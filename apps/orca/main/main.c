/* Orca main-CPU app: brings the display up, then streams a Bosch BMM350
 * magnetometer wired to the breakout I2C bus (I2C0, GPIO 16 SDA / 17 SCL).
 *
 * Output goes to THIS CPU's own USB serial port (product ID 2054, not the
 * display's 2055). Until the sensor answers, every two seconds it prints which
 * I2C addresses respond, then tries to start the sensor again. Once running it
 * prints one line per sample, raw counts only (the laptop converts to uT):
 *
 *     MAG <seq> <t_ms> <x> <y> <z> <temp> <drdy>
 *
 * The register values and the start-up sequence below are taken from Bosch's
 * BMM350_SensorAPI (BSD-3-Clause, github.com/boschsensortec/BMM350_SensorAPI,
 * bmm350.c / bmm350_defs.h), not from memory. Two things in that driver are easy
 * to miss and are done here:
 *   - every I2C read returns TWO dummy bytes before the register data, so a read
 *     of n bytes asks for n + 2 and skips the first two;
 *   - after the soft reset the sensor needs a magnetic reset (BR then FGR
 *     commands) before its data is valid.
 * Left out on purpose: Bosch's per-chip factory trim (OTP) compensation. The
 * values are therefore uncompensated: good for seeing that the field changes and
 * how, not for absolute microtesla.
 *
 * NOT YET RUN ON HARDWARE. */
#include "fwog_main.h"
#include "pico/stdlib.h"
#include <stdio.h>
#include <string.h>

FWOG_WATCHDOG_DEFAULT();

/* ---- BMM350 constants (Bosch bmm350_defs.h) ---- */
#define BMM_ADDR_A         0x14u     /* ADSEL low  */
#define BMM_ADDR_B         0x15u     /* ADSEL high */
#define BMM_REG_CHIP_ID    0x00u
#define BMM_REG_AGGR_SET   0x04u     /* ODR in bits 3:0, averaging in bits 5:4 */
#define BMM_REG_AXIS_EN    0x05u     /* bit 0 X, bit 1 Y, bit 2 Z */
#define BMM_REG_PMU_CMD    0x06u
#define BMM_REG_PMU_STAT0  0x07u     /* bits 7:5 = the command last accepted */
#define BMM_REG_INT_STATUS 0x30u     /* bit 2 = data ready */
#define BMM_REG_MAG_X      0x31u     /* X, Y, Z, temperature: 4 x 24-bit little endian */
#define BMM_REG_OTP_CMD    0x50u
#define BMM_REG_CMD        0x7Eu
#define BMM_CHIP_ID        0x33u
#define BMM_CMD_SOFTRESET  0xB6u
#define BMM_OTP_PWR_OFF    0x80u
#define BMM_PMU_SUSPEND    0x00u
#define BMM_PMU_NORMAL     0x01u
#define BMM_PMU_UPD_OAE    0x02u
#define BMM_PMU_FGR        0x05u
#define BMM_PMU_BR         0x07u
#define BMM_ODR_50HZ       0x5u
#define BMM_AVG_4          0x2u
#define BMM_DATA_BYTES     12u
#define BMM_DUMMY_BYTES    2u

#define SCAN_EVERY_MS      2000u
#define SAMPLE_EVERY_MS    20u       /* 50 Hz, the sensor's output rate */
#define MAX_FOUND          16u

static uint8_t s_addr = BMM_ADDR_A;

static void wait_ms(uint32_t ms) {
    sleep_ms(ms);
    board_watchdog_kick();           /* the start-up waits add up to about 150 ms */
}

static bool bmm_write(uint8_t reg, uint8_t value) {
    return fwog_i2c_write_reg(s_addr, reg, value);
}

/* Read n bytes starting at reg, skipping the two dummy bytes the chip sends first. */
static bool bmm_read(uint8_t reg, uint8_t *dst, size_t n) {
    uint8_t buf[BMM_DATA_BYTES + BMM_DUMMY_BYTES];
    if (n == 0u || n > BMM_DATA_BYTES) return false;
    if (!fwog_i2c_read_regs(s_addr, reg, buf, n + BMM_DUMMY_BYTES)) return false;
    memcpy(dst, buf + BMM_DUMMY_BYTES, n);
    return true;
}

static bool bmm_pmu_is(uint8_t command) {
    uint8_t st;
    if (!bmm_read(BMM_REG_PMU_STAT0, &st, 1u)) return false;
    return (uint8_t)((st >> 5) & 0x7u) == command;
}

/* Soft reset, check the chip ID, magnetic reset, set 50 Hz, normal mode.
 * Tries both possible addresses. Prints which step failed. */
static bool bmm_start(void) {
    bool found = false;
    const uint8_t addrs[2] = { BMM_ADDR_A, BMM_ADDR_B };
    for (unsigned i = 0; i < 2u && !found; i++) {
        s_addr = addrs[i];
        wait_ms(3);
        if (!bmm_write(BMM_REG_CMD, BMM_CMD_SOFTRESET)) continue;
        wait_ms(24);
        uint8_t id = 0;
        if (bmm_read(BMM_REG_CHIP_ID, &id, 1u) && id == BMM_CHIP_ID) {
            found = true;
        } else {
            DIAG("[orca_main] 0x%02x answered, chip id 0x%02x (want 0x%02x)\n",
                 (unsigned)s_addr, (unsigned)id, (unsigned)BMM_CHIP_ID);
        }
    }
    if (!found) return false;

    (void)bmm_write(BMM_REG_OTP_CMD, BMM_OTP_PWR_OFF);

    /* Magnetic reset: only allowed from suspend, which is where a reset leaves it. */
    if (!bmm_write(BMM_REG_PMU_CMD, BMM_PMU_BR)) return false;
    wait_ms(14);
    if (!bmm_pmu_is(BMM_PMU_BR)) { DIAG("[orca_main] BMM350: bit reset not accepted\n"); return false; }
    if (!bmm_write(BMM_REG_PMU_CMD, BMM_PMU_FGR)) return false;
    wait_ms(18);
    if (!bmm_pmu_is(BMM_PMU_FGR)) { DIAG("[orca_main] BMM350: flux guide reset not accepted\n"); return false; }

    if (!bmm_write(BMM_REG_AGGR_SET, (uint8_t)(BMM_ODR_50HZ | (BMM_AVG_4 << 4)))) return false;
    if (!bmm_write(BMM_REG_PMU_CMD, BMM_PMU_UPD_OAE)) return false;
    wait_ms(1);
    if (!bmm_write(BMM_REG_AXIS_EN, 0x07u)) return false;
    if (!bmm_write(BMM_REG_PMU_CMD, BMM_PMU_NORMAL)) return false;
    wait_ms(38);
    DIAG("[orca_main] BMM350 running at 0x%02x, 50 Hz\n", (unsigned)s_addr);
    return true;
}

static int32_t signed24(const uint8_t *p) {
    int32_t v = (int32_t)((uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16));
    if (v & 0x800000) v -= 0x1000000;
    return v;
}

static void report_i2c(void) {
    uint8_t found[MAX_FOUND];
    const size_t n = fwog_i2c_scan(found, MAX_FOUND);   /* bounded by timeouts */
    char list[MAX_FOUND * 6u + 1u];
    size_t len = 0;
    list[0] = '\0';
    for (size_t i = 0; i < n && i < MAX_FOUND; i++) {
        len += (size_t)snprintf(list + len, sizeof list - len, " 0x%02x", (unsigned)found[i]);
    }
    DIAG("[orca_main] I2C0 devices (%u):%s\n", (unsigned)n, n ? list : " none");
}

int main(void) {
    board_init();
    fwog_display_result_t d = fwog_display_update_run();
    board_init_i2c();                   /* breakout I2C0, GPIO 16/17 */

    const absolute_time_t announce_until = make_timeout_time_ms(10000);
    absolute_time_t next_announce = get_absolute_time();
    absolute_time_t next_scan = make_timeout_time_ms(SCAN_EVERY_MS);
    bool mag_ok = false;
    uint32_t seq = 0;

    while (true) {
        board_watchdog_kick();          /* required: see watchdog.h */
        if (!time_reached(announce_until) && time_reached(next_announce)) {
            next_announce = make_timeout_time_ms(500);
            DIAG("[orca_main] display: %s\n", fwog_display_result_text(d));
        }

        if (!mag_ok) {
            if (time_reached(next_scan)) {
                next_scan = make_timeout_time_ms(SCAN_EVERY_MS);
                report_i2c();
                board_watchdog_kick();  /* a scan with a dead bus can take about a second */
                mag_ok = bmm_start();
            }
            sleep_ms(100);
            continue;
        }

        uint8_t status = 0, raw[BMM_DATA_BYTES];
        if (bmm_read(BMM_REG_INT_STATUS, &status, 1u) && bmm_read(BMM_REG_MAG_X, raw, BMM_DATA_BYTES)) {
#if FWOG_DIAG == FWOG_DIAG_USB
            /* Do not print into a USB port nobody is reading: it can block. */
            if (stdio_usb_connected())
#endif
            {
                DIAG("MAG %lu %lu %ld %ld %ld %ld %u\n", (unsigned long)seq,
                     (unsigned long)to_ms_since_boot(get_absolute_time()),
                     (long)signed24(raw), (long)signed24(raw + 3),
                     (long)signed24(raw + 6), (long)signed24(raw + 9),
                     (unsigned)((status >> 2) & 1u));
            }
            seq++;
        } else {
            DIAG("[orca_main] BMM350 read failed; restarting it\n");
            mag_ok = false;
            next_scan = make_timeout_time_ms(SCAN_EVERY_MS);
        }
        sleep_ms(SAMPLE_EVERY_MS);
    }
}

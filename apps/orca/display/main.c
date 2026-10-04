/* Orca display app: the OG as feedback screen and button pad.
 *
 * A dumb terminal for the laptop's rehab engine -- see rehab_proto.h for the
 * protocol. It draws what it is told, reports button edges, and does nothing
 * else. Rehab logic belongs on the host so that this CPU, which must never
 * have a watchdog, has nothing in it that can wedge.
 *
 * The red-button power-off path is the stock one: fwog_power_poll() runs
 * every iteration and its return value is the ONLY source of button edges
 * (calling fwog_buttons_poll() as well would eat the hold machine's edges).
 *
 * NOT YET RUN ON HARDWARE. Per AGENTS.md, the 6 s red-hold power-off must be
 * observed on a real board before anything else in this app is trusted. */
#include "fwog_display.h"
#include "pico/stdlib.h"
#include "rehab_proto.h"
#include <stdio.h>

FWOG_POWER_DEFAULT();

#define GLYPH_SCALE 3u
#define ROW_PX      (LCD_GLYPH_H * GLYPH_SCALE)      /* 24 */
#define BAR_Y       (ST7789_H - 12u)
#define BAR_H       8u

static const char *const kBtnName[FWOG_BTN_COUNT] = {
    "gray", "yellow", "green", "blue", "red",
};

static bool     s_lcd_ready;
static bool     s_accel_ok;
static bool     s_audio_ok;

/* BEEP: i2s_audio_init() fixes the sample rate at 8000 Hz (see apps/bench). The
   buffer must outlive the command, because the driver reads from it while the
   note plays. 300 ms at 8 kHz = 2400 samples = 4.8 KB. */
#define BEEP_RATE_HZ   8000u
#define BEEP_MAX_MS    300u
#define BEEP_MAX_N     (BEEP_RATE_HZ * BEEP_MAX_MS / 1000u)
#define BEEP_AMPLITUDE 6000
#define MIN_BRIGHT_PCT 10u      /* never fully dark: a black screen looks like a dead OG */
static int16_t s_beep[BEEP_MAX_N];
static unsigned s_stream_hz;     /* 0 = accelerometer stream off */
static uint32_t s_next_acc_ms;
static uint32_t s_acc_seq;

/* Battery: one `BAT <mV> <usb 0|1>` line every few seconds while a host is attached. */
#define BAT_PERIOD_MS 5000u
static bool     s_bat_ok;
static uint32_t s_next_bat_ms;
static uint16_t s_fg, s_bg, s_accent;

/* IMG: one rectangle of raw RGB565 from the host. Static, not a stack local:
   30 KB would overflow the stack, and nothing here is reentrant. */
#define IMG_TIMEOUT_MS 250u
static uint16_t s_img[REHAB_IMG_MAX_PIXELS];
static bool     s_img_active;
static unsigned s_img_x, s_img_y, s_img_w, s_img_h;
static size_t   s_img_need, s_img_got;   /* bytes */
static uint32_t s_img_last_ms;          /* last time a payload byte arrived */

static void draw_row(unsigned row, const char *text) {
    if (!s_lcd_ready) return;
    lcd_text_draw_padded(0, (uint16_t)(row * ROW_PX), text, REHAB_COLS,
                         GLYPH_SCALE, s_fg, s_bg);
}

static void draw_bar(unsigned pct) {
    if (!s_lcd_ready) return;
    const uint16_t full = (uint16_t)(ST7789_W - 2u);
    const uint16_t fill = (uint16_t)((full * pct) / 100u);
    if (fill > 0) st7789_fill_rect(1, BAR_Y, fill, BAR_H, s_accent);
    if (fill < full) st7789_fill_rect((uint16_t)(1u + fill), BAR_Y,
                                      (uint16_t)(full - fill), BAR_H, s_bg);
}

static void img_finish(void) {
    if (s_lcd_ready) {
        st7789_set_window((uint16_t)s_img_x, (uint16_t)s_img_y,
                          (uint16_t)s_img_w, (uint16_t)s_img_h);
        st7789_blit(s_img, (size_t)s_img_w * s_img_h);
    }
    s_img_active = false;
    printf("OK\n");
}

/* A short square-wave beep, integer maths only. The last fifth fades out so the
   note does not end with a click. Returns false if the speaker is not up. */
static bool beep(unsigned hz, unsigned ms, unsigned vol) {
    if (!s_audio_ok) return false;
    if (vol == 0u) return true;                  /* muted: nothing to play, nothing wrong */
    unsigned n = BEEP_RATE_HZ * ms / 1000u;
    if (n > BEEP_MAX_N) n = BEEP_MAX_N;
    const unsigned half = BEEP_RATE_HZ / (2u * hz);          /* samples per half period */
    const unsigned fade = n / 5u;
    for (unsigned i = 0; i < n; i++) {
        int32_t s = (((i / (half ? half : 1u)) & 1u) ? -BEEP_AMPLITUDE : BEEP_AMPLITUDE);
        if (fade != 0u && i >= n - fade) s = s * (int32_t)(n - i) / (int32_t)fade;
        s_beep[i] = (int16_t)s;
    }
    /* A note still in flight is cut off, the same way apps/ogvegas does it; start
       refuses while one is playing. */
    if (!i2s_audio_is_idle()) i2s_audio_stop();
    i2s_audio_set_volume((int)vol);
    return i2s_audio_start(s_beep, n, true, false);
}

static void handle_line(char *line) {
    rehab_msg_t m;
    rehab_parse(line, &m);
    switch (m.cmd) {
    case REHAB_CMD_NONE:  return;
    case REHAB_CMD_IMG:
        /* Switch from lines to raw bytes. The reply is sent once the pixels
           have arrived and been drawn, not now. */
        s_img_x = m.x; s_img_y = m.y; s_img_w = m.w; s_img_h = m.h;
        s_img_need = (size_t)m.w * m.h * 2u;
        s_img_got = 0;
        s_img_last_ms = to_ms_since_boot(get_absolute_time());
        s_img_active = true;
        return;
    case REHAB_CMD_PING:  printf("OK pong\n"); return;
    case REHAB_CMD_CLS:
        if (s_lcd_ready) { st7789_clear(s_bg); st7789_dma_wait(); }
        printf("OK\n");
        return;
    case REHAB_CMD_TXT:   draw_row(m.row, m.text); printf("OK\n"); return;
    case REHAB_CMD_BAR:   draw_bar(m.pct);         printf("OK\n"); return;
    case REHAB_CMD_BRIGHT: {
        const unsigned pct = m.pct < MIN_BRIGHT_PCT ? MIN_BRIGHT_PCT : m.pct;
        board_backlight((uint8_t)(pct * 255u / 100u));
        printf("OK\n");
        return;
    }
    case REHAB_CMD_ROT:
        if (s_lcd_ready) {
            st7789_set_rotation(m.rot180);
            st7789_clear(s_bg);              /* old pixels are in the old orientation */
            st7789_dma_wait();
        }
        printf("OK\n");
        return;
    case REHAB_CMD_BEEP:
        if (beep(m.hz, m.ms, m.vol)) printf("OK\n");
        else                         printf("ERR audio\n");
        return;
    case REHAB_CMD_MODE:
        s_accent = m.limb_mode ? st7789_rgb565(255, 160, 0)
                               : st7789_rgb565(0, 200, 120);
        printf("OK\n");
        return;
    case REHAB_CMD_STREAM:
        if (m.hz != 0u && !s_accel_ok) { printf("ERR accel not-initialised\n"); return; }
        s_stream_hz   = m.hz;
        s_next_acc_ms = to_ms_since_boot(get_absolute_time());
        s_acc_seq     = 0u;
        printf("OK\n");
        return;
    case REHAB_CMD_ERROR: printf("ERR %s\n", m.err); return;
    }
}

int main(void) {
    board_init();

    /* Without this the 6 s red hold has no LED countdown (power_poll.c draws
       it only when ws2812_ready()), so there is nothing to show the hold
       registered. Same call as the workshop's button-lights exercise. */
    ws2812_init(pio0, 0);

    lis3dh_init();
    s_accel_ok = lis3dh_configure(LIS3DH_RANGE_2G);

    /* Only turns the charger's ADC on so the battery voltage can be read; it changes no
       charging settings (bq25896_start_charging() would, so it is not called here). */
    s_bat_ok = bq25896_adc_continuous_enable();

    /* The speaker. Same state machine as apps/bench (pio0, sm 2; sm 0 is the LEDs). A
       failure only means no beeps: BEEP then answers ERR audio. */
    s_audio_ok = i2s_audio_init(pio0, 2u);

    /* Bounded wait for a host: pico_stdio_usb drops output until DTR. */
#if FWOG_DIAG == FWOG_DIAG_USB
    const absolute_time_t host_deadline = make_timeout_time_ms(5000);
    while (!stdio_usb_connected() && !time_reached(host_deadline)) {
        tight_loop_contents();
    }
    sleep_ms(300);
#endif

    st7789_init_begin();
    const absolute_time_t lcd_deadline = make_timeout_time_ms(500);
    while (!st7789_ready() && !time_reached(lcd_deadline)) st7789_init_step();
    s_lcd_ready = st7789_ready();

    s_fg     = st7789_rgb565(255, 255, 255);
    s_bg     = st7789_rgb565(0, 0, 0);
    s_accent = st7789_rgb565(0, 200, 120);
    if (s_lcd_ready) {
        st7789_clear(s_bg);
        st7789_dma_wait();
        board_backlight(255);
        draw_row(0, "Orca");
        draw_row(1, "waiting for host");
    }
    DIAG("[orca_display] alive lcd=%s accel=%s audio=%s battery=%s\n",
         s_lcd_ready ? "ok" : "FAILED", s_accel_ok ? "ok" : "FAILED",
         s_audio_ok ? "ok" : "FAILED", s_bat_ok ? "ok" : "FAILED");

    rehab_lines_t lines;
    rehab_lines_init(&lines);

    while (true) {
        const uint32_t now = to_ms_since_boot(get_absolute_time());
        const fwog_power_t pw = fwog_power_poll(now);

        for (unsigned id = 0; id < FWOG_BTN_COUNT; id++) {
            if (pw.buttons.pressed & FWOG_BTN_BIT(id))
                printf("BTN %s down\n", kBtnName[id]);
            if (pw.buttons.released & FWOG_BTN_BIT(id))
                printf("BTN %s up\n", kBtnName[id]);
        }

#if FWOG_DIAG == FWOG_DIAG_USB
        if (s_bat_ok && (int32_t)(now - s_next_bat_ms) >= 0) {
            s_next_bat_ms = now + BAT_PERIOD_MS;
            bq25896_telemetry_t bat;
            if (stdio_usb_connected() && bq25896_read_all(&bat))
                printf("BAT %u %u\n", (unsigned)bat.vbat_mv, bat.vbus_attached ? 1u : 0u);
        }
#endif

        /* Raw accelerometer lines, only while the host asked for them. If the
           host goes away, stop: printf to a USB port nobody reads can block,
           and this loop also runs the power-off hold. */
#if FWOG_DIAG == FWOG_DIAG_USB
        if (s_stream_hz != 0u && !stdio_usb_connected()) s_stream_hz = 0u;
#endif
        if (s_stream_hz != 0u && (int32_t)(now - s_next_acc_ms) >= 0) {
            s_next_acc_ms = now + 1000u / s_stream_hz;
            lis3dh_sample_t smp;
            smp.x = smp.y = smp.z = 0x7FFF;   /* no real reading is 0x7FFF */
            if (lis3dh_process(LIS3DH_MOVE_THRESHOLD_DEFAULT, &smp, NULL) &&
                (smp.x != 0x7FFF || smp.y != 0x7FFF || smp.z != 0x7FFF)) {
                printf("ACC %lu %lu %d %d %d\n", (unsigned long)s_acc_seq++,
                       (unsigned long)now, (int)smp.x, (int)smp.y, (int)smp.z);
            }
        }

        /* Drain whatever the host has sent, without blocking. */
        for (;;) {
            if (s_img_active) {
                /* Pixels: take whatever is waiting, up to 256 bytes at a time.
                   One getchar per byte measured only ~138 KB/s over USB. */
                size_t want = s_img_need - s_img_got;
                if (want > 256u) want = 256u;
                int n = stdio_get_until((char *)s_img + s_img_got, (int)want,
                                        get_absolute_time());
                if (n <= 0) break;                       /* nothing waiting */
                s_img_got += (size_t)n;
                s_img_last_ms = now;
                if (s_img_got >= s_img_need) img_finish();
                continue;
            }
            int c = getchar_timeout_us(0);
            if (c == PICO_ERROR_TIMEOUT) break;
            int r = rehab_lines_feed(&lines, (char)c);
            if (r == 1)       handle_line(lines.buf);
            else if (r == -1) printf("ERR line-too-long\n");
        }

        /* A picture that stopped arriving is dropped, not waited for: this
           loop also runs the power-off hold, and there is no watchdog here. */
        if (s_img_active && (int32_t)(now - s_img_last_ms) > (int32_t)IMG_TIMEOUT_MS) {
            s_img_active = false;
            printf("ERR img-timeout\n");
        }

        /* Feed the speaker's DMA chain; it parks itself when a note ends. */
        if (s_audio_ok) i2s_audio_process();

        /* No rest while pixels are arriving: 2 ms per pass would cap the
           stream at the size of the USB receive buffer per 2 ms. */
        if (!s_img_active) sleep_ms(2);
    }
}

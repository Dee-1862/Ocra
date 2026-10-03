/* WiliRehab display app: the OG as feedback screen and button pad.
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
static uint16_t s_fg, s_bg, s_accent;

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

static void handle_line(char *line) {
    rehab_msg_t m;
    rehab_parse(line, &m);
    switch (m.cmd) {
    case REHAB_CMD_NONE:  return;
    case REHAB_CMD_PING:  printf("OK pong\n"); return;
    case REHAB_CMD_CLS:
        if (s_lcd_ready) { st7789_clear(s_bg); st7789_dma_wait(); }
        printf("OK\n");
        return;
    case REHAB_CMD_TXT:   draw_row(m.row, m.text); printf("OK\n"); return;
    case REHAB_CMD_BAR:   draw_bar(m.pct);         printf("OK\n"); return;
    case REHAB_CMD_MODE:
        s_accent = m.limb_mode ? st7789_rgb565(255, 160, 0)
                               : st7789_rgb565(0, 200, 120);
        printf("OK\n");
        return;
    case REHAB_CMD_ERROR: printf("ERR %s\n", m.err); return;
    }
}

int main(void) {
    board_init();

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
        draw_row(0, "WiliRehab");
        draw_row(1, "waiting for host");
    }
    DIAG("[wilirehab_display] alive lcd=%s\n", s_lcd_ready ? "ok" : "FAILED");

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

        /* Drain whatever the host has sent, without blocking. */
        for (int c = getchar_timeout_us(0); c != PICO_ERROR_TIMEOUT;
             c = getchar_timeout_us(0)) {
            int r = rehab_lines_feed(&lines, (char)c);
            if (r == 1)       handle_line(lines.buf);
            else if (r == -1) printf("ERR line-too-long\n");
        }
        sleep_ms(2);
    }
}

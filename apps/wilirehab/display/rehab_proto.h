/* WiliRehab host<->OG line protocol: pure parsing, no SDK, host-tested by
 * tests/test_rehab_proto.c.
 *
 * Text lines over the display CPU's USB CDC port, one command per line, in
 * the same OK/ERR style as apps/bench:
 *
 *   host -> OG                       OG -> host
 *   PING                             OK pong
 *   CLS                              OK
 *   TXT <row> <text...>              OK        (row 0..REHAB_ROWS-1)
 *   BAR <0..100>                     OK        (progress bar along the bottom)
 *   MODE <hand|limb>                 OK
 *   IMG <x> <y> <w> <h>              OK        (then exactly w*h*2 raw bytes: RGB565,
 *                                              little-endian, row by row. No newline
 *                                              after the pixels. See below.)
 *   BRIGHT <0..100>                  OK        (backlight percent; the OG never goes below 10)
 *   BEEP <hz> <ms> <vol>             OK        (a square-wave beep: hz 100..4000, ms 1..300,
 *                                              vol 0..10; ERR audio if the speaker did not start)
 *   STREAM <0..100>                  OK        (accelerometer lines per second; 0 = off)
 *                                    ACC <seq> <t_ms> <x> <y> <z>   (raw int16, see lis3dh.h)
 *                                    BTN <gray|yellow|green|blue|red> <down|up>
 *                                    ERR <reason>
 *
 * The OG is deliberately a dumb terminal: all rehab logic lives on the laptop
 * (wilirehab/host). Keeping it that way means the display CPU runs no policy
 * that could hang, and it has no watchdog to recover it. */
#ifndef WILIREHAB_PROTO_H
#define WILIREHAB_PROTO_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define REHAB_ROWS     8u     /* text rows at scale 3 on the 320x240 panel */
#define REHAB_COLS     17u    /* 320 / (6*3) = 17 */
#define REHAB_LINE_MAX 96u

/* The panel, and the largest picture one IMG command may carry. IMG is how the
 * laptop draws anything that is not text: menus, games, the face preview. It
 * sends only the rectangles that changed, each at most this many pixels (a 320
 * wide band 48 rows tall). The receiver holds one such rectangle in RAM. If the
 * bytes stop mid-picture the receiver gives up after a timeout and goes back to
 * reading lines, so a lost byte cannot wedge it; the host sends a newline before
 * every command so any stray bytes are dropped as an empty or unknown line. */
#define REHAB_SCREEN_W        320u
#define REHAB_SCREEN_H        240u
#define REHAB_IMG_MAX_PIXELS  (320u * 48u)

typedef enum {
    REHAB_CMD_NONE = 0,       /* blank line */
    REHAB_CMD_PING,
    REHAB_CMD_CLS,
    REHAB_CMD_TXT,
    REHAB_CMD_BAR,
    REHAB_CMD_MODE,
    REHAB_CMD_STREAM,
    REHAB_CMD_IMG,            /* x, y, w, h set; w*h*2 payload bytes follow */
    REHAB_CMD_BRIGHT,         /* pct set */
    REHAB_CMD_BEEP,           /* hz, ms, vol set */
    REHAB_CMD_ERROR           /* `err` points at the reason */
} rehab_cmd_t;

typedef struct {
    rehab_cmd_t cmd;
    unsigned    x, y, w, h;   /* IMG, already checked to lie on the panel */
    unsigned    row;          /* TXT */
    unsigned    pct;          /* BAR, 0..100 */
    unsigned    hz;           /* STREAM: 0..100, 0 turns it off. BEEP: 100..4000 */
    unsigned    ms, vol;      /* BEEP: 1..300 and 0..10 */
    bool        limb_mode;    /* MODE */
    const char *text;         /* TXT: points into the parsed line */
    const char *err;          /* ERROR */
} rehab_msg_t;

/* Parse one NUL-terminated line. Trailing CR/LF are tolerated. `line` is
 * modified in place and must outlive `out` (out->text points into it). */
void rehab_parse(char *line, rehab_msg_t *out);

/* Accumulates bytes into lines. An over-long line is dropped whole (and
 * reported) rather than split, so a truncated tail can never be parsed as a
 * command of its own. */
typedef struct {
    char     buf[REHAB_LINE_MAX];
    size_t   len;
    bool     overflow;
} rehab_lines_t;

void rehab_lines_init(rehab_lines_t *l);

/* Feed one byte. Returns 1 when a line is complete (NUL-terminated in
 * l->buf, accumulator reset for the next byte), -1 when an over-long line
 * was dropped, 0 otherwise. */
int rehab_lines_feed(rehab_lines_t *l, char c);

#endif

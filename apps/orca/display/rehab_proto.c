#include "rehab_proto.h"
#include <string.h>

static bool is_space(char c) { return c == ' ' || c == '\t'; }

static char *skip_space(char *p) {
    while (is_space(*p)) p++;
    return p;
}

/* Split off the next token: returns it NUL-terminated and advances *rest past
 * it. Returns NULL when nothing is left. */
static char *token(char **rest) {
    char *p = skip_space(*rest);
    if (*p == '\0') { *rest = p; return NULL; }
    char *start = p;
    while (*p != '\0' && !is_space(*p)) p++;
    if (*p != '\0') *p++ = '\0';
    *rest = p;
    return start;
}

static bool parse_uint(const char *s, unsigned max, unsigned *out) {
    if (s == NULL || *s == '\0') return false;
    unsigned v = 0;
    for (; *s != '\0'; s++) {
        if (*s < '0' || *s > '9') return false;
        v = v * 10u + (unsigned)(*s - '0');
        if (v > max) return false;
    }
    *out = v;
    return true;
}

static void fail(rehab_msg_t *out, const char *why) {
    out->cmd = REHAB_CMD_ERROR;
    out->err = why;
}

void rehab_parse(char *line, rehab_msg_t *out) {
    memset(out, 0, sizeof *out);

    size_t n = strlen(line);
    while (n > 0 && (line[n - 1] == '\r' || line[n - 1] == '\n')) line[--n] = '\0';

    char *rest = line;
    char *verb = token(&rest);
    if (verb == NULL) { out->cmd = REHAB_CMD_NONE; return; }

    if (strcmp(verb, "PING") == 0) { out->cmd = REHAB_CMD_PING; return; }
    if (strcmp(verb, "CLS") == 0)  { out->cmd = REHAB_CMD_CLS;  return; }

    if (strcmp(verb, "TXT") == 0) {
        unsigned row;
        if (!parse_uint(token(&rest), REHAB_ROWS - 1u, &row)) { fail(out, "bad-row"); return; }
        out->cmd  = REHAB_CMD_TXT;
        out->row  = row;
        /* Everything after the row, spaces inside it preserved. */
        out->text = skip_space(rest);
        return;
    }

    if (strcmp(verb, "BAR") == 0) {
        unsigned pct;
        if (!parse_uint(token(&rest), 100u, &pct)) { fail(out, "bad-percent"); return; }
        out->cmd = REHAB_CMD_BAR;
        out->pct = pct;
        return;
    }

    if (strcmp(verb, "IMG") == 0) {
        unsigned x, y, w, h;
        if (!parse_uint(token(&rest), REHAB_SCREEN_W - 1u, &x) ||
            !parse_uint(token(&rest), REHAB_SCREEN_H - 1u, &y) ||
            !parse_uint(token(&rest), REHAB_SCREEN_W, &w) ||
            !parse_uint(token(&rest), REHAB_SCREEN_H, &h)) {
            fail(out, "bad-image");
            return;
        }
        /* Written so none of it can wrap: the limits above bound every term. */
        if (w == 0u || h == 0u || x + w > REHAB_SCREEN_W || y + h > REHAB_SCREEN_H ||
            w * h > REHAB_IMG_MAX_PIXELS) {
            fail(out, "bad-image");
            return;
        }
        out->cmd = REHAB_CMD_IMG;
        out->x = x; out->y = y; out->w = w; out->h = h;
        return;
    }

    if (strcmp(verb, "STREAM") == 0) {
        unsigned hz;
        if (!parse_uint(token(&rest), 100u, &hz)) { fail(out, "bad-rate"); return; }
        out->cmd = REHAB_CMD_STREAM;
        out->hz  = hz;
        return;
    }

    if (strcmp(verb, "BRIGHT") == 0) {
        unsigned pct;
        if (!parse_uint(token(&rest), 100u, &pct)) { fail(out, "bad-percent"); return; }
        out->cmd = REHAB_CMD_BRIGHT;
        out->pct = pct;
        return;
    }

    if (strcmp(verb, "ROT") == 0) {
        unsigned deg;
        if (!parse_uint(token(&rest), 180u, &deg) || (deg != 0u && deg != 180u)) {
            fail(out, "bad-rotation");
            return;
        }
        out->cmd = REHAB_CMD_ROT;
        out->rot180 = (deg == 180u);
        return;
    }

    if (strcmp(verb, "BEEP") == 0) {
        unsigned hz, ms, vol;
        if (!parse_uint(token(&rest), 4000u, &hz) || hz < 100u ||
            !parse_uint(token(&rest), 300u, &ms) || ms < 1u ||
            !parse_uint(token(&rest), 10u, &vol)) {
            fail(out, "bad-beep");
            return;
        }
        out->cmd = REHAB_CMD_BEEP;
        out->hz = hz; out->ms = ms; out->vol = vol;
        return;
    }

    if (strcmp(verb, "MODE") == 0) {
        char *m = token(&rest);
        if (m != NULL && strcmp(m, "hand") == 0) {
            out->cmd = REHAB_CMD_MODE; out->limb_mode = false; return;
        }
        if (m != NULL && strcmp(m, "limb") == 0) {
            out->cmd = REHAB_CMD_MODE; out->limb_mode = true; return;
        }
        fail(out, "bad-mode");
        return;
    }

    fail(out, "unknown-command");
}

void rehab_lines_init(rehab_lines_t *l) {
    l->len = 0;
    l->overflow = false;
}

int rehab_lines_feed(rehab_lines_t *l, char c) {
    if (c == '\n') {
        if (l->overflow) {
            l->overflow = false;
            l->len = 0;
            return -1;
        }
        l->buf[l->len] = '\0';
        l->len = 0;
        return 1;
    }
    if (l->overflow) return 0;
    if (l->len >= REHAB_LINE_MAX - 1u) { l->overflow = true; return 0; }
    l->buf[l->len++] = c;
    return 0;
}

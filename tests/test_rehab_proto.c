/* Host tests for the WiliRehab line protocol (apps/wilirehab/display). */
#include "test_util.h"
#include "rehab_proto.h"
#include <string.h>

static rehab_msg_t parse(const char *src, char *scratch, size_t n) {
    strncpy(scratch, src, n - 1);
    scratch[n - 1] = '\0';
    rehab_msg_t m;
    rehab_parse(scratch, &m);
    return m;
}

int main(void) {
    char b[REHAB_LINE_MAX * 2];
    rehab_msg_t m;

    m = parse("PING\r\n", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_PING);
    m = parse("", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_NONE);
    m = parse("   \r", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_NONE);
    m = parse("CLS", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_CLS);

    m = parse("TXT 2 Angle 34 deg", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_TXT);
    ASSERT_EQ(m.row, 2);
    ASSERT_TRUE(strcmp(m.text, "Angle 34 deg") == 0);
    m = parse("TXT 7 x", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_TXT);
    m = parse("TXT 8 x", b, sizeof b);          /* one past the last row */
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);
    m = parse("TXT x hi", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);
    m = parse("TXT", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);
    m = parse("TXT 1", b, sizeof b);            /* empty text clears the row */
    ASSERT_EQ(m.cmd, REHAB_CMD_TXT);
    ASSERT_TRUE(m.text[0] == '\0');

    m = parse("BAR 0", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_BAR);
    ASSERT_EQ(m.pct, 0);
    m = parse("BAR 100", b, sizeof b);
    ASSERT_EQ(m.pct, 100);
    m = parse("BAR 101", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);
    m = parse("BAR -1", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);
    m = parse("BAR 99999999999", b, sizeof b);  /* must not wrap */
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);

    m = parse("MODE limb", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_MODE);
    ASSERT_TRUE(m.limb_mode);
    m = parse("MODE hand", b, sizeof b);
    ASSERT_TRUE(!m.limb_mode);
    m = parse("MODE other", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);

    m = parse("FROB", b, sizeof b);
    ASSERT_EQ(m.cmd, REHAB_CMD_ERROR);

    /* Line accumulator: two lines, then an over-long one dropped whole. */
    rehab_lines_t l;
    rehab_lines_init(&l);
    const char *s = "PING\nCLS\n";
    int ready = 0;
    for (; *s; s++) ready += (rehab_lines_feed(&l, *s) == 1);
    ASSERT_EQ(ready, 2);

    for (unsigned i = 0; i < REHAB_LINE_MAX + 10; i++) rehab_lines_feed(&l, 'A');
    ASSERT_EQ((unsigned)(rehab_lines_feed(&l, '\n') == -1), 1);
    /* The tail of the long line must not leak into the next one. */
    for (const char *p = "PING"; *p; p++) rehab_lines_feed(&l, *p);
    ASSERT_EQ(rehab_lines_feed(&l, '\n'), 1);
    ASSERT_TRUE(strcmp(l.buf, "PING") == 0);

    TEST_RETURN();
}

/* WiliRehab main-CPU app. For now this only does what every main app owes
 * the board: kick the watchdog and bring the display up (which streams the
 * embedded display image). The IMU pods on the Maestro Qwiic port will be
 * read here once the display half has been seen working on hardware. */
#include "fwog_main.h"
#include "pico/stdlib.h"

FWOG_WATCHDOG_DEFAULT();

int main(void) {
    board_init();
    fwog_display_result_t d = fwog_display_update_run();

    const absolute_time_t announce_until = make_timeout_time_ms(10000);
    while (true) {
        board_watchdog_kick();      /* required: see watchdog.h */
        if (!time_reached(announce_until)) {
            DIAG("[wilirehab_main] display: %s\n", fwog_display_result_text(d));
        }
        sleep_ms(500);
    }
}

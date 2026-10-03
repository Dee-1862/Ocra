# WiliRehab: the OG as feedback screen for a laptop-side rehab engine
# (see /wilirehab). Display and main halves live together because the main
# UF2 carries the display image inside it.
add_executable(wilirehab_display display/main.c display/rehab_proto.c)
target_link_libraries(wilirehab_display fwog_display_bsp)
fwog_display_app(wilirehab_display
    VERSION 001
    DESCRIPTION "WiliRehab feedback screen and button pad, driven by the laptop over USB CDC")

add_executable(wilirehab_main main/main.c)
target_link_libraries(wilirehab_main fwog_main_bsp)
fwog_embed_display_image(wilirehab_main)
fwog_main_app(wilirehab_main
    VERSION 001
    DESCRIPTION "WiliRehab main half: watchdog and display bring-up (IMU pods to come)")

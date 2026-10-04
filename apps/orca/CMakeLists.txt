# Orca: the OG as feedback screen for a laptop-side rehab engine
# (see /orca). Display and main halves live together because the main
# UF2 carries the display image inside it.
add_executable(orca_display display/main.c display/rehab_proto.c)
target_link_libraries(orca_display fwog_display_bsp)
fwog_display_app(orca_display
    VERSION 002
    DESCRIPTION "Orca feedback screen and button pad, driven by the laptop over USB CDC; draws text rows and IMG pictures")

add_executable(orca_main main/main.c)
target_link_libraries(orca_main fwog_main_bsp)
fwog_embed_display_image(orca_main)
fwog_main_app(orca_main
    VERSION 002
    DESCRIPTION "Orca main half: watchdog and display bring-up (IMU pods to come)")

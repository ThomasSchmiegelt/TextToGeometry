# SPDX-License-Identifier: LGPL-2.1-or-later

# Build/install the TextToGeometry add-on as part of a FreeCAD build.
#
# NOTE: This add-on also works standalone. The easiest way to install it into
# an existing FreeCAD is:
#
#     python3 install.py            # finds the Mod directories itself
#     python3 install.py --target /pfad/zu/FreeCAD/Mod
#
# Keep the file list below in step with FILES/DIRS in install.py.

IF (BUILD_GUI)
    fc_copy_sources(TextToGeometry "${CMAKE_BINARY_DIR}/Mod/TextToGeometry"
        __init__.py
        Init.py
        InitGui.py
        T2GCore.py
        T2GCommand.py
        T2GSkills.py
        T2GProject.py
        T2GAgent.py
        install.py
        package.xml
        README.md
        DOKUMENTATION.md
        Resources/icons/text-to-geometry.svg
        Resources/icons/t2g-panel.svg
        Resources/icons/t2g-chat.svg
        Resources/icons/t2g-project.svg
        Resources/icons/t2g-generate.svg
        Resources/icons/t2g-skill-build.svg
        Resources/icons/t2g-skill-learn.svg
        Resources/icons/t2g-skill-design.svg
        Resources/icons/t2g-backend.svg
        Resources/drawings/bridge.svg
        Resources/licenses/LGPL-2.1-or-later.txt
        Skills/bruecke/bruecke.py
    )

    INSTALL(
        DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/Resources
                  ${CMAKE_CURRENT_SOURCE_DIR}/Skills
        DESTINATION Mod/TextToGeometry
        FILES_MATCHING PATTERN "*.py" PATTERN "*.svg" PATTERN "*.txt"
    )
ENDIF (BUILD_GUI)

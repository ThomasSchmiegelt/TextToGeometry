# SPDX-License-Identifier: LGPL-2.1-or-later

# Build/install the TextToGeometry add-on as part of a FreeCAD build.
#
# NOTE: This add-on also works standalone — simply copy this directory into
# FreeCAD's Mod/ folder (e.g. ~/.local/share/FreeCAD/Mod/TextToGeometry).

IF (BUILD_GUI)
    fc_copy_sources(TextToGeometry "${CMAKE_BINARY_DIR}/Mod/TextToGeometry"
        Init.py
        InitGui.py
        T2GCore.py
        T2GCommand.py
        package.xml
        README.md
        Resources/icons/text-to-geometry.svg
        Resources/licenses/LGPL-2.1-or-later.txt
    )
ENDIF (BUILD_GUI)

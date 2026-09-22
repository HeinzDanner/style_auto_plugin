# -*- coding: utf-8 -*-
#
# Style Auto Plugin
# Copyright (C) 2026 Heinz Danner
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# See the LICENSE file for more details.
"""Style Auto Plugin init."""

# noinspection PyDocstring,PyPep8Naming
def classFactory(iface):
    from .style_auto_plugin import StyleAutoPlugin
    return StyleAutoPlugin(iface)

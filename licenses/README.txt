Third-party notices used by desktop distributions
================================================

pygame-ce 2.5.8 and its dependency notices are copied verbatim from:
https://github.com/pygame-community/pygame-ce/tree/2.5.8/docs/licenses
https://github.com/pygame-community/pygame-ce/blob/2.5.8/docs/LGPL.txt

Source code and build instructions:
https://github.com/pygame-community/pygame-ce/tree/2.5.8

The build extra pins pygame-ce 2.5.8 to keep these notices paired with the
packaged runtime. Updating that pin requires reviewing the notices too.
Some upstream notices describe optional components not used by this engine.
The exact native libraries vary between Windows, Linux, and macOS wheels.
Before a public release, review the native dependency licenses for the target
platform and any additional assets/plugins you have added.

The builder also copies the installed Python LICENSE.txt and PyInstaller's
COPYING.txt into the distribution. PyInstaller's bootloader has a special
exception permitting distribution of commercial/proprietary frozen programs;
see the complete terms in its COPYING.txt.

The demo font has its own notice in game/gui/LICENSE-DejaVu.txt.
The engine and original demo assets use the repository's MIT LICENSE.

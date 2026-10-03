#!/bin/zsh
# Puts the Prem Lab icon on the launcher (tools/prem-lab.command), or on any file you name, so it looks like an app in Finder and on the Desktop.
#
#   tools/set-icon.sh                                the launcher
#   tools/set-icon.sh ~/Desktop/"Prem Lab.command"   a copy of it
#
# macOS keeps a custom icon beside the file, not inside it, so Git does not carry it: run this once after cloning the project, and again if a
# pull replaces the launcher. A shortcut made with `ln -s` (or Finder's Make Alias) shows the icon of the file it points to.
# To go back to the plain icon: select the file in Finder, press Cmd+I, click the icon at the top left of the info window and press Delete.

HERE="${0:A:h}"
ICON="$HERE/icon/prem-lab.icns"
TARGET="${1:-$HERE/prem-lab.command}"

[[ "$(uname)" == "Darwin" ]] || { echo "Custom icons are a macOS feature; there is nothing to do here."; exit 1; }
[[ -e "$TARGET" ]] || { echo "Cannot find $TARGET"; exit 1; }
[[ -f "$ICON" ]] || { echo "Cannot find the icon ($ICON)."; exit 1; }

osascript -l JavaScript -e '
ObjC.import("AppKit");
function run(argv) {
  const [icon, file] = argv;
  const image = $.NSImage.alloc.initWithContentsOfFile(icon);
  if (!image.isValid) throw new Error("cannot read " + icon);
  if (!$.NSWorkspace.sharedWorkspace.setIconForFileOptions(image, file, 0)) throw new Error("macOS would not change the icon of " + file);
}' "$ICON" "${TARGET:A}" || exit 1

echo "Prem Lab icon set on ${TARGET:A}"

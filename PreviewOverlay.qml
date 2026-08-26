pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons

PanelWindow {
  id: root

  property var hostPanel: null
  property var anchorItem: null
  property var screenshots: []
  property int currentIndex: -1
  property bool open: false

  readonly property var anchorWindow: anchorItem ? anchorItem.QsWindow.window : null

  readonly property var currentScreenshot: root.currentIndex >= 0 && root.currentIndex < root.screenshots.length
    ? root.screenshots[root.currentIndex]
    : null
  readonly property string currentPath: currentScreenshot ? currentScreenshot.path : ""
  readonly property int previewWidth: previewImage.sourceSize.width
  readonly property int previewHeight: previewImage.sourceSize.height
  readonly property color foreground: Color.foreground
  readonly property color dim: Qt.darker(Color.foreground, 1.5)
  readonly property color scrim: Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 0.82)

  visible: root.open
  screen: root.anchorWindow ? root.anchorWindow.screen : null
  anchors { top: true; bottom: true; left: true; right: true }
  color: "transparent"
  WlrLayershell.namespace: "omarchy-screenshot-preview"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: root.open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
  exclusionMode: ExclusionMode.Ignore

  function showAt(index) {
    if (root.screenshots.length === 0) return
    root.currentIndex = index < 0 ? 0 : Math.min(index, root.screenshots.length - 1)
    root.open = true
  }

  function step(delta) {
    if (root.screenshots.length === 0) return
    var next = root.currentIndex + delta
    if (next < 0) next = root.screenshots.length - 1
    if (next >= root.screenshots.length) next = 0
    root.currentIndex = next
  }

  function dismiss() {
    root.open = false
  }

  Rectangle {
    anchors.fill: parent
    color: root.scrim

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    Item {
      id: stage
      anchors.fill: parent
      anchors.margins: Style.space(48)
      focus: true

      Keys.priority: Keys.BeforeItem
      Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Escape || event.key === Qt.Key_Return) {
          root.dismiss()
        } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
          root.step(-1)
        } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
          root.step(1)
        }
        event.accepted = true
      }

      ColumnLayout {
        anchors.fill: parent
        spacing: Style.spacing.lg

        Rectangle {
          Layout.fillWidth: true
          Layout.fillHeight: true
          color: "transparent"
          border.color: Color.popups.border
          border.width: Math.max(1, Style.space(1))
          radius: Style.cornerRadius
          clip: true

          Image {
            id: previewImage
            anchors.fill: parent
            anchors.margins: Style.space(8)
            source: root.currentPath ? "file://" + root.currentPath : ""
            fillMode: Image.PreserveAspectFit
            smooth: true
          }
        }

        RowLayout {
          Layout.fillWidth: true
          spacing: Style.spacing.lg

          Text {
            Layout.fillWidth: true
            text: currentScreenshot ? currentScreenshot.name : ""
            color: root.foreground
            font.family: Style.fontFamily
            font.pixelSize: Style.font.body
            elide: Text.ElideRight
          }

          Text {
            text: currentScreenshot
              ? (root.previewWidth > 0
                  ? root.previewWidth + "×" + root.previewHeight + "  ·  "
                  : "")
                + (currentScreenshot.humanSize || "") + "  ·  "
                + (root.currentIndex + 1) + "/" + root.screenshots.length
              : ""
            color: root.dim
            font.family: Style.fontFamily
            font.pixelSize: Style.font.caption
            Layout.alignment: Qt.AlignVCenter
          }
        }
      }
    }
  }
}

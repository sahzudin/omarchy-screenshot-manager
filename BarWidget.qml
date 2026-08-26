import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "io.github.sahzudin.omarchy-screenshot-manager"

  property var screenshotState: Model.emptyState()

  readonly property string barIcon: setting("icon", Model.defaultIcon())
  readonly property bool showCount: setting("showCount", true) !== false

  readonly property bool opened: panelLoader.item
    ? panelLoader.item.opened === true
    : false
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true
    : false

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function toggle() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  function applyState(state) {
    screenshotState = state || Model.emptyState()
  }

  function refresh() {
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function takeScreenshot() {
    if (panelLoader.item && panelLoader.item.takeScreenshot)
      panelLoader.item.takeScreenshot()
  }

  function copyLatest() {
    if (panelLoader.item && panelLoader.item.copyLatest)
      panelLoader.item.copyLatest()
  }

  function previewLatest() {
    if (panelLoader.item && panelLoader.item.previewLatest)
      panelLoader.item.previewLatest()
  }

  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = root.bar
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: "io.github.sahzudin.omarchy-screenshot-manager"

    function refresh(): void { root.refresh() }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function preview(): void { root.previewLatest() }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Model.barLabel(root.screenshotState.count, root.vertical, root.screenshotState.known, root.barIcon, root.showCount)
    tooltipText: "Screenshots · left: manage · right: new · middle: copy latest"
    horizontalMargin: 8.75
    verticalPadding: 8.75

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.toggle()
      else if (buttonCode === Qt.RightButton) root.takeScreenshot()
      else if (buttonCode === Qt.MiddleButton) root.copyLatest()
    }
  }
}
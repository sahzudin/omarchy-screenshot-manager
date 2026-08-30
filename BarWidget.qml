import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "io.github.sahzudin.omarchy-screenshot-manager"

  property var screenshotState: Model.emptyState()

  readonly property string barIcon: setting("icon", Model.defaultIcon())
  readonly property bool showCount: setting("showCount", true) !== false
  readonly property bool highlightNew: setting("highlightNew", false) === true

  // What the watcher last saw on disk, which is a different question from the
  // list the panel holds: this one is answered while the panel is shut.
  property var watchState: Model.emptyStatus()
  readonly property bool hasNew: root.highlightNew
    && !root.opened
    && root.watchState.newCount > 0

  readonly property string helperPath: Model.scriptPath(Qt.resolvedUrl("screenshotctl.py"))

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

  function applyStatus(status) {
    watchState = status || Model.emptyStatus()
  }

  // A bar surface is built per monitor, so this widget is live once per screen
  // and every copy would otherwise run the same directory scan on the same
  // timer. One instance polls and hands the answer to its peers; the rest only
  // draw it.
  function watchPeers() {
    return bar && typeof bar.moduleWidgets === "function"
      ? bar.moduleWidgets(moduleName)
      : []
  }

  function publishStatus(status) {
    var peers = watchPeers()
    if (peers.length === 0) {
      applyStatus(status)
      return
    }
    for (var i = 0; i < peers.length; i++) {
      if (peers[i] && peers[i].applyStatus) peers[i].applyStatus(status)
    }
  }

  function pollWatch() {
    if (watchProcess.running) return
    var peers = watchPeers()
    if (peers.length > 0 && peers[0] !== root) return
    watchProcess.command = [root.helperPath, "status"]
    watchProcess.running = true
  }

  // Clicking the widget is the whole acknowledgement: whichever button was
  // pressed, the user has looked at the bar and knows something is there.
  function markSeen() {
    if (!root.highlightNew) return
    publishStatus(Model.seenStatus(root.watchState))
    if (seenProcess.running) return
    seenProcess.command = [root.helperPath, "seen"]
    seenProcess.running = true
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

  // Screenshots taken while the list was open have been seen by definition, so
  // closing the panel settles the marker rather than leaving them to light the
  // bar up the moment it shuts.
  onOpenedChanged: if (!root.opened) root.markSeen()

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

  // Runs only while the marker is switched on, so leaving `highlightNew` off
  // costs nothing. `triggeredOnStart` seeds the marker the first time it is
  // enabled, which is what stops an existing folder from all counting as new.
  Timer {
    id: watchTimer
    interval: 5000
    repeat: true
    triggeredOnStart: true
    running: root.highlightNew
    onTriggered: root.pollWatch()
  }

  Process {
    id: watchProcess
    command: ["true"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) root.publishStatus(Model.parseStatus(text))
    }
  }

  Process {
    id: seenProcess
    command: ["true"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) root.publishStatus(Model.parseStatus(text))
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
    tooltipText: Model.barTooltip(root.hasNew ? root.watchState.newCount : 0)
    horizontalMargin: 8.75
    verticalPadding: 8.75

    // Nothing added beside the glyph: the glyph itself is recoloured, which is
    // the mechanism the bar's own indicators already use to say a thing wants
    // you, and it leaves the row of icons exactly the shape it was. Accent
    // rather than the inherited urgent, because a screenshot is not an
    // emergency.
    active: root.hasNew
    activeColor: Color.accent

    onPressed: function(buttonCode) {
      root.markSeen()
      if (buttonCode === Qt.LeftButton) root.toggle()
      else if (buttonCode === Qt.RightButton) root.takeScreenshot()
      else if (buttonCode === Qt.MiddleButton) root.copyLatest()
    }
  }
}

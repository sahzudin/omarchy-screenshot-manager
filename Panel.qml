pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "io.github.sahzudin.omarchy-screenshot-manager"
  ipcTarget: "io.github.sahzudin.omarchy-screenshot-manager"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var screenshots: []
  property var visibleScreenshots: []
  property string filterText: ""
  property string statusText: ""
  property string pendingTrashKey: ""
  property var pendingTrashScreenshot: null
  property string listError: ""
  property string trashError: ""
  property string copyError: ""
  property string clearError: ""
  property bool pendingClear: false
  property bool loaded: false
  property string lastSignature: ""

  readonly property var barIdentity: hostWidget || root
  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property color contentDim: Qt.darker(contentForeground, 1.5)
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool busy: listProcess.running || trashProcess.running || copyProcess.running || clearProcess.running
  readonly property bool previewOpen: preview ? preview.open : false
  readonly property string helperPath: {
    var url = decodeURIComponent(String(Qt.resolvedUrl("screenshotctl.py")))
    return url.indexOf("file://") === 0 ? url.substring(7) : url
  }

  function helperCommand(args) {
    return [root.helperPath].concat(args || [])
  }

  function updateVisible() {
    root.visibleScreenshots = Model.filterScreenshots(root.screenshots, root.filterText)
  }

  function open() {
    root.controller.show()
    refresh()
    preview.anchorItem = root.anchorItem
    preview.hostPanel = root
    Qt.callLater(function() {
      if (root.opened && !root.previewOpen) searchField.forceActiveFocus()
    })
  }

  function close() {
    resetTrashConfirmation()
    if (preview) preview.dismiss()
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function refresh() {
    if (root.busy) return
    if (!root.loaded) root.statusText = "Scanning screenshots…"
    root.listError = ""
    listProcess.command = helperCommand(["list"])
    listProcess.running = true
  }

  function applyState(raw) {
    var state = Model.parseState(raw)
    var first = state.screenshots.length > 0 ? state.screenshots[0].path : ""
    var last = state.screenshots.length > 0 ? state.screenshots[state.screenshots.length - 1].path : ""
    var signature = state.dir + "|" + state.count + "|" + first + "|" + last
    if (signature !== root.lastSignature) {
      root.lastSignature = signature
      root.screenshots = state.screenshots
      root.updateVisible()
    }
    root.screenshotsDir = state.dir
    root.loaded = state.known
    root.statusText = state.count === 0
      ? "No screenshots yet"
      : state.total === state.count
        ? state.dirName + " · " + state.count + " screenshots"
        : state.dirName + " · " + state.total + " screenshots (showing " + state.count + ")"
    if (root.hostWidget && root.hostWidget.applyState) root.hostWidget.applyState(state)
  }

  function copyScreenshot(screenshot) {
    if (root.busy || !screenshot) return
    resetTrashConfirmation()
    root.statusText = "Copying " + screenshot.name + "…"
    root.copyError = ""
    copyProcess.command = helperCommand(["copy", screenshot.path])
    copyProcess.running = true
  }

  function copyLatest() {
    if (root.busy) return
    if (root.screenshots.length === 0) {
      root.statusText = "No screenshots to copy yet"
      return
    }
    root.copyScreenshot(root.screenshots[0])
  }

  function requestTrash(screenshot) {
    if (root.busy || !screenshot) return
    var key = Model.screenshotKey(screenshot)
    if (root.pendingTrashKey !== key) {
      root.pendingTrashKey = key
      root.pendingTrashScreenshot = screenshot
      root.statusText = "Press Confirm to trash " + screenshot.name
      confirmTimer.restart()
      return
    }

    confirmTimer.stop()
    root.statusText = "Trashing " + screenshot.name + "…"
    root.trashError = ""
    trashProcess.command = helperCommand(["trash", screenshot.path])
    trashProcess.running = true
  }

  function resetTrashConfirmation() {
    confirmTimer.stop()
    root.pendingTrashKey = ""
    root.pendingTrashScreenshot = null
    root.pendingClear = false
  }

  function requestClearAll() {
    if (root.busy || root.screenshots.length === 0) return
    if (root.pendingTrashKey) resetTrashConfirmation()
    if (!root.pendingClear) {
      root.pendingClear = true
      root.statusText = "Press Clear all again to trash " + root.screenshots.length + " screenshots"
      confirmTimer.restart()
      return
    }

    confirmTimer.stop()
    root.pendingClear = false
    root.statusText = "Trashing " + root.screenshots.length + " screenshots…"
    root.clearError = ""
    clearProcess.command = helperCommand(["clear"])
    clearProcess.running = true
  }

  function takeScreenshot() {
    if (root.busy) return
    resetTrashConfirmation()
    root.statusText = "Launching screenshot flow…"
    Quickshell.execDetached("omarchy capture screenshot")
    takeRefreshTimer.restart()
  }

  function openFolder() {
    if (!root.screenshotsDir) return
    Quickshell.execDetached(["xdg-open", root.screenshotsDir])
  }

  function openPreviewAt(index) {
    if (root.busy || root.visibleScreenshots.length === 0) return
    resetTrashConfirmation()
    preview.screenshots = root.visibleScreenshots
    preview.showAt(index < 0 ? 0 : index)
  }

  function openPreview(screenshot) {
    if (root.busy || !screenshot) return
    var index = -1
    for (var i = 0; i < root.visibleScreenshots.length; i++) {
      if (root.visibleScreenshots[i].path === screenshot.path) {
        index = i
        break
      }
    }
    root.openPreviewAt(index)
  }

  function previewLatest() {
    if (root.visibleScreenshots.length === 0) {
      root.statusText = "No screenshots to preview yet"
      return
    }
    root.openPreviewAt(0)
  }

  property string screenshotsDir: ""

  onAnchorItemChanged: if (preview) preview.anchorItem = root.anchorItem
  onFilterTextChanged: root.updateVisible()

  Timer {
    id: confirmTimer
    interval: 8000
    onTriggered: {
      root.resetTrashConfirmation()
      if (!root.busy) root.statusText = "Trash cancelled"
    }
  }

  Timer {
    id: takeRefreshTimer
    interval: 10000
    onTriggered: root.refresh()
  }

  Timer {
    id: autoRefreshTimer
    interval: 5000
    repeat: true
    running: root.opened && !root.busy && !root.previewOpen
    onTriggered: root.refresh()
  }

  Process {
    id: listProcess
    command: ["true"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) root.applyState(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.listError = text
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) root.statusText = Model.actionError(exitCode, root.listError, "load")
    }
  }

  Process {
    id: trashProcess
    command: ["true"]
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.trashError = text
    }
    onExited: function(exitCode) {
      var trashed = root.pendingTrashScreenshot
      root.resetTrashConfirmation()
      if (exitCode !== 0) {
        root.statusText = Model.actionError(exitCode, root.trashError, "trash")
        return
      }
      root.statusText = "Trashed " + (trashed ? trashed.name : "screenshot")
      Qt.callLater(root.refresh)
    }
  }

  Process {
    id: copyProcess
    command: ["true"]
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.copyError = text
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.statusText = Model.actionError(exitCode, root.copyError, "copy")
        return
      }
      root.statusText = "Copied to clipboard as PNG"
    }
  }

  Process {
    id: clearProcess
    command: ["true"]
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.clearError = text
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.statusText = Model.actionError(exitCode, root.clearError, "clear")
        return
      }
      root.statusText = "Trashed all screenshots"
      Qt.callLater(root.refresh)
    }
  }

  PreviewOverlay {
    id: preview
    hostPanel: root
    anchorItem: root.anchorItem
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: searchField
    contentWidth: panel.fittedContentWidth(Style.space(520))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      anchors.fill: parent
      blocked: searchField.activeFocus || root.previewOpen
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(12)

        RowLayout {
          width: parent.width
          spacing: Style.space(8)

          Text {
            text: root.hostWidget && root.hostWidget.barIcon
              ? root.hostWidget.barIcon
              : Model.defaultIcon()
            color: root.contentForeground
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.heading
            Layout.alignment: Qt.AlignVCenter
          }

          ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space(1)

            Text {
              Layout.fillWidth: true
              text: "Screenshot Manager"
              color: root.contentForeground
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.subtitle
              font.bold: true
            }

            Text {
              Layout.fillWidth: true
              text: root.statusText || "List, preview, copy, and delete screenshots"
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }
          }

          PanelActionButton {
            iconText: "󰐕"
            tooltipText: "Take a screenshot"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            enabled: !root.busy
            onClicked: root.takeScreenshot()
          }

          PanelActionButton {
            iconText: "󰝰"
            tooltipText: "Open screenshots folder"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            enabled: root.screenshotsDir !== ""
            onClicked: root.openFolder()
          }

          PanelActionButton {
            iconText: "󰑐"
            tooltipText: "Refresh"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            enabled: !root.busy
            onClicked: root.refresh()
          }

          PanelActionButton {
            iconText: root.pendingClear ? "󰄬" : "󰩹"
            tooltipText: root.pendingClear
              ? "Confirm clearing all screenshots"
              : "Clear all screenshots"
            bordered: root.pendingClear
            foreground: Color.urgent
            hoverColor: Color.urgent
            fontFamily: root.contentFontFamily
            enabled: !root.busy && root.screenshots.length > 0
            onClicked: root.requestClearAll()
          }
        }

        TextField {
          id: searchField
          width: parent.width
          placeholderText: "Filter screenshots…"
          maximumLength: 100
          foreground: root.contentForeground
          font.family: root.contentFontFamily
          enabled: !root.busy
          onTextChanged: root.filterText = text
          onAccepted: if (root.visibleScreenshots.length > 0) root.openPreviewAt(0)
          Keys.onEscapePressed: root.close()
        }

        PanelSeparator {
          width: parent.width
          foreground: root.contentForeground
        }

        RowLayout {
          width: parent.width

          Text {
            Layout.fillWidth: true
            text: "SCREENSHOTS"
            color: root.contentDim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            font.letterSpacing: 1
          }

          Text {
            visible: root.busy
            text: "Working…"
            color: root.contentDim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Text {
          visible: !root.busy && root.visibleScreenshots.length === 0
          width: parent.width
          text: root.filterText
            ? "No screenshots match your filter."
            : "Take a screenshot with omarchy capture screenshot (or right-click the bar icon)."
          color: root.contentDim
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.WordWrap
        }

        ListView {
          id: screenshotList
          visible: root.visibleScreenshots.length > 0
          width: parent.width
          height: Math.min(contentHeight, Style.space(320))
          model: root.visibleScreenshots
          spacing: Style.space(4)
          clip: true
          boundsBehavior: Flickable.StopAtBounds

          delegate: Rectangle {
            id: screenshotRow
            required property int index
            required property var modelData
            readonly property string itemKey: Model.screenshotKey(modelData)

            width: screenshotList.width
            height: screenshotContent.implicitHeight + Style.space(10)
            color: Style.controlFill(false, screenshotHover.hovered, root.contentForeground, Color.accent)
            radius: Style.cornerRadius

            HoverHandler { id: screenshotHover }

            MouseArea {
              anchors.fill: parent
              onDoubleClicked: root.openPreviewAt(screenshotRow.index)
            }

            RowLayout {
              id: screenshotContent
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: Style.space(8)
              anchors.rightMargin: Style.space(8)
              spacing: Style.space(8)

              Rectangle {
                width: Style.space(84)
                height: Style.space(48)
                radius: Style.space(4)
                color: Util.alpha(Color.background, 0.5)
                clip: true
                Layout.alignment: Qt.AlignVCenter

                Image {
                  anchors.fill: parent
                  source: screenshotRow.modelData.path ? "file://" + screenshotRow.modelData.path : ""
                  fillMode: Image.PreserveAspectCrop
                  smooth: true
                }
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: Style.space(1)

                Text {
                  Layout.fillWidth: true
                  text: screenshotRow.modelData.name
                  color: root.contentForeground
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                }

                Text {
                  Layout.fillWidth: true
                  text: Model.screenshotMeta(screenshotRow.modelData)
                  color: root.contentDim
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
              }

              PanelActionButton {
                iconText: "󰌉"
                tooltipText: "Preview"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                enabled: !root.busy
                onClicked: root.openPreviewAt(screenshotRow.index)
              }

              PanelActionButton {
                iconText: "󰅌"
                tooltipText: "Copy to clipboard"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                enabled: !root.busy
                onClicked: root.copyScreenshot(screenshotRow.modelData)
              }

              PanelActionButton {
                iconText: screenshotRow.itemKey === root.pendingTrashKey ? "󰄬" : "󰩹"
                tooltipText: screenshotRow.itemKey === root.pendingTrashKey
                  ? "Confirm trash"
                  : "Move to trash"
                bordered: screenshotRow.itemKey === root.pendingTrashKey
                foreground: Color.urgent
                hoverColor: Color.urgent
                fontFamily: root.contentFontFamily
                enabled: !root.busy
                onClicked: root.requestTrash(screenshotRow.modelData)
              }
            }
          }
        }

        Text {
          width: parent.width
          text: "Screenshots are copied to the clipboard as PNG · Trashed files stay in the desktop trash."
          color: root.contentDim
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
      }
    }
  }
}

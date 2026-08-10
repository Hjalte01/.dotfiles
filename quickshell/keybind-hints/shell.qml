import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

ShellRoot {
    id: root

    property bool overlayVisible: false
    property bool pinned: false
    property bool contextual: false
    property string mode: "all"
    property string pendingMode: "all"
    property var entries: []
    property double peekBlockedUntil: 0

    readonly property color base: "#f01e1e2e"
    readonly property color surface: "#313244"
    readonly property color overlay: "#45475a"
    readonly property color text: "#cdd6f4"
    readonly property color subtext: "#a6adc8"
    readonly property color mauve: "#cba6f7"
    readonly property color blue: "#89b4fa"
    readonly property color green: "#a6e3a1"
    readonly property color border: "#6c7086"

    readonly property var allColumns: [
        { title: "Launch & open", groups: ["Launch & open", "Sequences"] },
        { title: "Windows & layout", groups: ["Windows & layout"] },
        { title: "Workspaces", groups: ["Workspaces"] },
        { title: "Clipboard & automation", groups: ["Clipboard & Codex", "Accessibility & automation"] },
        { title: "Desktop", groups: ["Display & desktop"] },
        { title: "Capture & hardware", groups: ["Notifications & screenshots", "Hardware & media"] }
    ]

    readonly property var superColumns: [
        { title: "Launch & open", groups: ["Launch & open"] },
        { title: "Windows & layout", groups: ["Windows & layout"] },
        { title: "Workspaces", groups: ["Workspaces"] },
        { title: "Clipboard & automation", groups: ["Clipboard & Codex", "Accessibility & automation"] },
        { title: "Desktop", groups: ["Display & desktop"] },
        { title: "Capture & hardware", groups: ["Notifications & screenshots", "Hardware & media"] }
    ]

    readonly property var activeColumns: mode === "super" ? superColumns : allColumns
    readonly property bool contextMode: mode === "web" || mode === "audio"

    function filteredEntries() {
        if (contextMode)
            return entries.filter(entry => entry.scope === mode)
        if (mode === "super")
            return entries.filter(entry => entry.scope === "super" && entry.combo.indexOf(" → ") === -1)
        return entries
    }

    function entriesForGroup(groupName) {
        return filteredEntries().filter(entry => entry.group === groupName)
    }

    function contextDestinations() {
        return entries.filter(entry => entry.scope === mode && keyLabel(entry) !== "Escape")
    }

    function keyLabel(entry) {
        if (contextMode) {
            const pieces = entry.combo.split(" → ")
            return pieces.length > 1 ? pieces[pieces.length - 1] : entry.display
        }
        if (mode === "super")
            return entry.combo.replace(/^Super\+/, "")
        return entry.combo
    }

    function titleText() {
        if (mode === "web")
            return "Web shortcuts"
        if (mode === "audio")
            return "Audio hierarchy"
        if (mode === "super")
            return "Super shortcuts"
        return "Desktop key map"
    }

    function subtitleText() {
        if (mode === "web")
            return "Choose a destination"
        if (mode === "audio")
            return "Choose a device manager"
        if (pinned)
            return "Pinned · Esc or Super+M closes · Super+Shift+M searches"
        return "Release Super to close · Super+M pins"
    }

    function loadAndShow(requestedMode) {
        pendingMode = requestedMode || "all"
        dataLoader.running = true
    }

    Process {
        id: dataLoader
        command: ["/home/hjalte/.local/bin/keybind-data"]

        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    root.entries = JSON.parse(text)
                    root.mode = root.pendingMode
                    root.overlayVisible = true
                } catch (error) {
                    console.error("keybind-hints: could not parse keybind data:", error)
                }
            }
        }
    }

    Connections {
        target: Hyprland

        function onRawEvent(event) {
            const dismissingEvent = event.name === "workspace"
                || event.name === "workspacev2"
                || event.name === "focusedmon"
                || event.name === "activewindow"
                || event.name === "activewindowv2"

            if (dismissingEvent) {
                // A Super chord can complete before the delayed peek IPC arrives.
                // Keep that late request from reopening the overlay after navigation.
                root.peekBlockedUntil = Date.now() + 500
                if (root.overlayVisible && !root.pinned && !root.contextual)
                    root.overlayVisible = false
            }
        }
    }

    IpcHandler {
        target: "overlay"

        function state(): string {
            return JSON.stringify({
                visible: root.overlayVisible,
                pinned: root.pinned,
                contextual: root.contextual,
                mode: root.mode,
                pendingMode: root.pendingMode,
                entries: root.entries.length,
                loaderRunning: dataLoader.running
            })
        }

        function show(requestedMode: string): void {
            root.loadAndShow(requestedMode)
        }

        function hide(): void {
            root.pinned = false
            root.contextual = false
            root.overlayVisible = false
        }

        function toggleAll(): void {
            if (root.pinned) {
                root.pinned = false
                root.overlayVisible = false
            } else {
                root.pinned = true
                root.contextual = false
                root.loadAndShow("all")
            }
        }

        function peek(): void {
            if (!root.pinned && !root.contextual && Date.now() >= root.peekBlockedUntil)
                root.loadAndShow("super")
        }

        function endPeek(): void {
            if (!root.pinned && !root.contextual)
                root.overlayVisible = false
        }

        function showContext(requestedMode: string): void {
            root.contextual = true
            root.loadAndShow(requestedMode)
        }

        function hideContext(): void {
            root.contextual = false
            if (root.pinned)
                root.loadAndShow("all")
            else
                root.overlayVisible = false
        }
    }

    component KeyRow: RowLayout {
        required property var entry
        Layout.fillWidth: true
        spacing: 10

        Rectangle {
            Layout.preferredWidth: Math.max(48, keyText.implicitWidth + 18)
            Layout.preferredHeight: 27
            radius: 6
            color: root.overlay
            border.color: "#585b70"
            border.width: 1

            Text {
                id: keyText
                anchors.centerIn: parent
                text: root.keyLabel(entry)
                color: root.mauve
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
        }

        Text {
            Layout.fillWidth: true
            text: entry.description
            color: root.text
            elide: Text.ElideRight
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: 12
        }
    }

    component KeySection: ColumnLayout {
        required property string groupName
        property var groupEntries: root.entriesForGroup(groupName)
        Layout.fillWidth: true
        spacing: 5
        visible: groupEntries.length > 0

        Text {
            Layout.topMargin: 7
            Layout.bottomMargin: 2
            text: groupName.toUpperCase()
            color: root.subtext
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: 10
            font.weight: Font.Bold
            font.letterSpacing: 0.7
        }

        Repeater {
            model: groupEntries

            KeyRow {
                required property var modelData
                entry: modelData
            }
        }
    }

    component HintColumn: Rectangle {
        required property var definition
        Layout.fillWidth: true
        Layout.fillHeight: true
        radius: 12
        color: root.surface
        border.color: "#45475a"
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 2

            Text {
                text: definition.title
                color: root.blue
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 15
                font.weight: Font.Bold
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 5
                Layout.bottomMargin: 2
                color: "#45475a"
            }

            Repeater {
                model: definition.groups

                KeySection {
                    required property var modelData
                    groupName: modelData
                }
            }

            Item { Layout.fillHeight: true }
        }
    }

    component WebTile: Rectangle {
        required property var entry
        Layout.fillWidth: true
        Layout.preferredHeight: 58
        radius: 11
        color: root.surface
        border.color: "#45475a"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.margins: 11
            spacing: 11

            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                radius: 8
                color: root.overlay
                border.color: root.mauve
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: root.keyLabel(entry)
                    color: root.mauve
                    font.family: "JetBrainsMono Nerd Font"
                    font.pixelSize: 14
                    font.weight: Font.Bold
                }
            }

            Text {
                Layout.fillWidth: true
                text: entry.description
                color: root.text
                elide: Text.ElideRight
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
    }

    Variants {
        model: Quickshell.screens

        PanelWindow {
            required property var modelData
            screen: modelData
            visible: root.overlayVisible
            color: "transparent"
            focusable: false
            exclusionMode: ExclusionMode.Ignore
            implicitHeight: root.contextMode ? 320 : Math.min(820, modelData.height * 0.78)

            anchors {
                left: true
                right: true
                bottom: true
            }

            margins {
                left: 42
                right: 42
                bottom: 38
            }

            Rectangle {
                id: card
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                width: root.contextMode ? Math.min(1120, parent.width) : parent.width
                height: parent.height
                color: root.base
                radius: 18
                border.color: root.mauve
                border.width: 2

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 22
                    spacing: 14

                    RowLayout {
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: 3

                            Text {
                                text: root.titleText()
                                color: root.text
                                font.family: "JetBrainsMono Nerd Font"
                                font.pixelSize: 23
                                font.weight: Font.Bold
                            }

                            Text {
                                text: root.subtitleText()
                                color: root.subtext
                                font.family: "JetBrainsMono Nerd Font"
                                font.pixelSize: 11
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Rectangle {
                            Layout.preferredWidth: countText.implicitWidth + 20
                            Layout.preferredHeight: 28
                            radius: 14
                            color: "#3b3d52"

                            Text {
                                id: countText
                                anchors.centerIn: parent
                                text: root.mode === "web" ? "Super + G"
                                    : root.mode === "audio" ? "Super + A"
                                    : root.filteredEntries().length + " bindings"
                                color: root.green
                                font.family: "JetBrainsMono Nerd Font"
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                        }
                    }

                    RowLayout {
                        visible: !root.contextMode
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.alignment: Qt.AlignLeft
                        spacing: 12

                        Repeater {
                            model: root.activeColumns

                            HintColumn {
                                required property var modelData
                                definition: modelData
                            }
                        }
                    }

                    GridLayout {
                        visible: root.contextMode
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        columns: root.mode === "audio" ? 2 : 5
                        columnSpacing: 10
                        rowSpacing: 10

                        Repeater {
                            model: root.contextDestinations()

                            WebTile {
                                required property var modelData
                                entry: modelData
                            }
                        }
                    }

                    Text {
                        visible: root.contextMode
                        Layout.alignment: Qt.AlignHCenter
                        text: "Esc  Cancel"
                        color: root.subtext
                        font.family: "JetBrainsMono Nerd Font"
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
}

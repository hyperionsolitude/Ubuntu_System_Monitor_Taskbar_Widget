import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3

PlasmoidItem {
    id: root

    property string statsText: "Loading stats..."
    property string displayText: statsText
    property string scriptPath: decodeURIComponent(Qt.resolvedUrl("../code/stats_once.py").toString().replace("file://", ""))
    property string currentCommand: ""

    preferredRepresentation: compactRepresentation
    Layout.minimumWidth: Kirigami.Units.gridUnit * 24
    Layout.preferredWidth: Math.max(Layout.minimumWidth, statsLabel.implicitWidth + (Kirigami.Units.smallSpacing * 2))

    compactRepresentation: Item {
        implicitWidth: Math.max(Kirigami.Units.gridUnit * 24, statsLabel.implicitWidth + (Kirigami.Units.smallSpacing * 2))
        implicitHeight: Math.max(statsLabel.implicitHeight, Kirigami.Units.gridUnit)
        Layout.minimumWidth: implicitWidth
        Layout.preferredWidth: implicitWidth

        PlasmaComponents3.Label {
            id: statsLabel
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            text: root.displayText
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideNone
            wrapMode: Text.NoWrap
            maximumLineCount: 1
            clip: true
        }
    }

    fullRepresentation: compactRepresentation

    Plasma5Support.DataSource {
        id: executable
        engine: "executable"

        onNewData: function (sourceName, data) {
            if (sourceName !== root.currentCommand) {
                return;
            }

            const out = (data["stdout"] || "").trim();
            const err = (data["stderr"] || "").trim();

            if (out.length > 0) {
                root.statsText = out;
                root.applyDisplayText();
            } else if (err.length > 0) {
                root.statsText = "Stats error";
                root.applyDisplayText();
            }

            disconnectSource(sourceName);
        }
    }

    function updateStats() {
        const command = "python3 \"" + root.scriptPath.replace(/"/g, "\\\"") + "\"";
        root.currentCommand = command;
        executable.connectSource(command);
    }

    function applyDisplayText() {
        // If the panel gives very little space, avoid "..." and show compact text.
        if (width < Kirigami.Units.gridUnit * 14) {
            root.displayText = "SYS";
        } else if (width < Kirigami.Units.gridUnit * 20) {
            root.displayText = root.statsText.replace("  ", " ").replace("  ", " ");
        } else {
            root.displayText = root.statsText;
        }
    }

    onWidthChanged: root.applyDisplayText()

    Timer {
        interval: 1000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: root.updateStats()
    }
}

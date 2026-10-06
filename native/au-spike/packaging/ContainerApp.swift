import AppKit

/// Build-only informational container; the packaging check never launches it.
@MainActor
final class ContainerDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let view = NSTextField(wrappingLabelWithString:
            "Guitar Gain Prototype\n\nExperimental gain-only Audio Unit bundle. " +
            "Restoration remains in the repository's offline tools. " +
            "Plugin loading and preset persistence are not qualified.")
        view.frame = NSRect(x: 24, y: 24, width: 432, height: 132)
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 480, height: 180))
        content.addSubview(view)
        let window = NSWindow(contentRect: content.bounds,
            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Guitar Gain Prototype"
        window.contentView = content
        window.center()
        window.makeKeyAndOrderFront(nil)
        self.window = window
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main
struct ContainerMain {
    @MainActor
    static func main() {
        let application = NSApplication.shared
        let delegate = ContainerDelegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { application.run() }
    }
}

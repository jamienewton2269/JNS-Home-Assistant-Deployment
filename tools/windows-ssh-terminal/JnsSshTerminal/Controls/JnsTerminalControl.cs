using System.Windows.Input;
using VirtualTerminal;
using VirtualTerminal.Buffer;

namespace JnsSshTerminal.Controls;

/// <summary>
/// VirtualTerminal with a small public scroll-position bridge so the JNS UI can
/// render a conventional vertical scrollbar without changing the upstream library.
/// </summary>
public sealed class JnsTerminalControl : TerminalControl
{
    private const int WheelLines = 3;
    private int _scrollOffset;

    public int ScrollOffset => _scrollOffset;

    public event EventHandler? ScrollPositionChanged;

    public void ScrollToOffset(int targetOffset)
    {
        int max = Session?.Buffer.ScrollbackCount ?? 0;
        targetOffset = Math.Clamp(targetOffset, 0, max);

        int delta = targetOffset - _scrollOffset;
        if (delta == 0)
            return;

        ScrollBy(delta);
        _scrollOffset = targetOffset;
        ScrollPositionChanged?.Invoke(this, EventArgs.Empty);
    }

    public void ResetTrackedScroll()
    {
        _scrollOffset = 0;
        ScrollToBottom();
        ScrollPositionChanged?.Invoke(this, EventArgs.Empty);
    }

    protected override void OnPreviewMouseWheel(MouseWheelEventArgs e)
    {
        bool localScroll = false;

        if (!e.Handled &&
            Session?.Decoder is TerminalDecoder decoder &&
            !Keyboard.Modifiers.HasFlag(ModifierKeys.Control))
        {
            bool appOwnsMouse =
                decoder.State.Modes.MouseTracking != MouseTrackingMode.Off &&
                !Keyboard.Modifiers.HasFlag(ModifierKeys.Shift);

            localScroll = !appOwnsMouse;
        }

        base.OnPreviewMouseWheel(e);

        if (!localScroll || e.Delta == 0)
            return;

        int max = Session?.Buffer.ScrollbackCount ?? 0;
        int direction = e.Delta > 0 ? 1 : -1;
        _scrollOffset = Math.Clamp(_scrollOffset + direction * WheelLines, 0, max);
        ScrollPositionChanged?.Invoke(this, EventArgs.Empty);
    }
}

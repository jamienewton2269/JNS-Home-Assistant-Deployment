using Renci.SshNet;
using System.Text;
using VirtualTerminal;

namespace JnsSshTerminal.Services;

public sealed class JnsSecureShellSession(ISshClient client) : SecureShellSession(client)
{
    public void PurgeLocalScreenBuffer(int restoreScrollbackLimit)
    {
        restoreScrollbackLimit = Math.Max(0, restoreScrollbackLimit);

        lock (Buffer.SyncRoot)
        {
            bool wasAlternate = Buffer.IsAlternate;

            // Drop every retained scrollback row first. SetScrollbackMax(0)
            // dequeues the ring and invalidates the cached snapshot.
            Buffer.SetScrollbackMax(0);

            // Clear both primary and alternate grids while finishing on the
            // same screen that was active before the purge.
            if (wasAlternate)
            {
                Buffer.ClearAll();
                Buffer.LeaveAlternateScreen();
                Buffer.ClearAll();
                Buffer.EnterAlternateScreen();
            }
            else
            {
                Buffer.ClearAll();
                Buffer.EnterAlternateScreen();
                Buffer.ClearAll();
                Buffer.LeaveAlternateScreen();
            }

            Buffer.SetScrollbackMax(restoreScrollbackLimit);
            Buffer.MarkAllDirty();

            if (Decoder is TerminalDecoder decoder)
            {
                decoder.State.CursorX = 0;
                decoder.State.CursorY = 0;
                decoder.State.WrapPending = false;
            }
        }

        NotifyBufferUpdated();
    }
}

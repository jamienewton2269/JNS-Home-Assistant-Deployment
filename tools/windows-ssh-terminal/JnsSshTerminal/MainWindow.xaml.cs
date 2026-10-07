using JnsSshTerminal.Models;
using JnsSshTerminal.Services;
using Microsoft.Win32;
using Renci.SshNet;
using Renci.SshNet.Common;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using VirtualTerminal;

namespace JnsSshTerminal;

public partial class MainWindow : Window
{
    private sealed class SessionSlot
    {
        public SessionSlot(string baseTitle, TabItem tab, TerminalControl terminal)
        {
            BaseTitle = baseTitle;
            Tab = tab;
            Terminal = terminal;
            Status = "Disconnected";
        }

        public string BaseTitle { get; }
        public TabItem Tab { get; }
        public TerminalControl Terminal { get; }

        public JnsSecureShellSession? Session { get; set; }
        public SshClient? Client { get; set; }
        public PrivateKeyFile? PrivateKeyFile { get; set; }
        public string Status { get; set; }
    }

    private readonly ProfileStore _profileStore = new();
    private readonly CommandHistoryStore _history = new();
    private readonly KnownHostsStore _knownHosts = new();

    private List<HostProfile> _profiles = new();
    private SessionSlot[] _slots = [];

    private SessionSlot ActiveSlot =>
        _slots[Math.Clamp(TerminalTabs.SelectedIndex, 0, _slots.Length - 1)];

    private TerminalControl ActiveTerminal => ActiveSlot.Terminal;

    public MainWindow()
    {
        InitializeComponent();

        _slots =
        [
            new SessionSlot("Terminal 1", TerminalTab1, Terminal1),
            new SessionSlot("Terminal 2", TerminalTab2, Terminal2)
        ];

        _profiles = _profileStore.Load();
        SavedHosts.ItemsSource = _profiles;

        _history.Load();
        HistoryList.ItemsSource = _history.Entries;

        UpdateActiveStatus();
    }

    private void SavedHosts_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (SavedHosts.SelectedItem is not HostProfile profile)
            return;

        ProfileName.Text = profile.Name;
        HostName.Text = profile.Host;
        Port.Text = profile.Port.ToString();
        Username.Text = profile.Username;
        KeyFile.Text = profile.KeyFile ?? "";
    }

    private void SaveHost_Click(object sender, RoutedEventArgs e)
    {
        if (!TryReadConnectionFields(out var name, out var host, out var port, out var username))
            return;

        var existing = _profiles.FirstOrDefault(p =>
            string.Equals(p.Name, name, StringComparison.OrdinalIgnoreCase));

        if (existing is null)
        {
            existing = new HostProfile();
            _profiles.Add(existing);
        }

        existing.Name = name;
        existing.Host = host;
        existing.Port = port;
        existing.Username = username;
        existing.KeyFile = string.IsNullOrWhiteSpace(KeyFile.Text) ? null : KeyFile.Text.Trim();

        _profiles = _profiles.OrderBy(p => p.Name, StringComparer.OrdinalIgnoreCase).ToList();
        _profileStore.Save(_profiles);
        SavedHosts.ItemsSource = null;
        SavedHosts.ItemsSource = _profiles;

        StatusText.Text = $"{ActiveSlot.BaseTitle}: host profile saved";
    }

    private void BrowseKey_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select SSH private key",
            CheckFileExists = true,
            Multiselect = false,
            Filter = "SSH keys|id_*;*.key;*.pem;*.ppk|All files|*.*"
        };

        if (dialog.ShowDialog(this) == true)
            KeyFile.Text = dialog.FileName;
    }

    private async void Connect_Click(object sender, RoutedEventArgs e)
    {
        if (!TryReadConnectionFields(out var profileName, out var host, out var port, out var username))
            return;

        if (string.IsNullOrWhiteSpace(KeyFile.Text) && string.IsNullOrEmpty(Password.Password))
        {
            MessageBox.Show(this,
                "Enter a password, or select a private key.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        var slot = ActiveSlot;
        await DisconnectSlotAsync(slot, updateUi: false);

        slot.Status = $"Connecting to {host}:{port}…";
        UpdateActiveStatus();

        string endpoint = $"{host}:{port}";
        KnownHostEntry? pendingTrust = null;
        string? hostKeyFailure = null;

        try
        {
            if (!string.IsNullOrWhiteSpace(KeyFile.Text))
            {
                string path = KeyFile.Text.Trim();
                slot.PrivateKeyFile = string.IsNullOrEmpty(Password.Password)
                    ? new PrivateKeyFile(path)
                    : new PrivateKeyFile(path, Password.Password);

                slot.Client = new SshClient(host, port, username, slot.PrivateKeyFile);
            }
            else
            {
                slot.Client = new SshClient(host, port, username, Password.Password);
            }

            slot.Client.HostKeyReceived += (_, args) =>
            {
                string fingerprint = args.FingerPrintSHA256;
                var known = _knownHosts.Find(endpoint);

                if (known is not null)
                {
                    bool matches =
                        string.Equals(known.FingerprintSha256, fingerprint, StringComparison.Ordinal) &&
                        string.Equals(known.Algorithm, args.HostKeyName, StringComparison.Ordinal);

                    args.CanTrust = matches;
                    if (!matches)
                    {
                        hostKeyFailure =
                            $"HOST KEY CHANGED for {endpoint}.\n\n" +
                            $"Expected SHA256:{known.FingerprintSha256}\n" +
                            $"Received SHA256:{fingerprint}\n\n" +
                            "Connection rejected.";
                    }

                    return;
                }

                bool accepted = Dispatcher.Invoke(() =>
                    MessageBox.Show(
                        this,
                        $"First connection to {endpoint}.\n\n" +
                        $"Algorithm: {args.HostKeyName}\n" +
                        $"SHA256:{fingerprint}\n\n" +
                        "Trust this host key?",
                        "Verify SSH host key",
                        MessageBoxButton.YesNo,
                        MessageBoxImage.Question) == MessageBoxResult.Yes);

                args.CanTrust = accepted;
                if (accepted)
                {
                    pendingTrust = new KnownHostEntry
                    {
                        Endpoint = endpoint,
                        Algorithm = args.HostKeyName,
                        FingerprintSha256 = fingerprint
                    };
                }
            };

            slot.Session = new JnsSecureShellSession(slot.Client);

            // The SSH transport and ShellStream must exist before the terminal
            // control is attached because attaching can immediately trigger Resize().
            await slot.Session.ConnectAsync();
            slot.Terminal.Session = slot.Session;

            if (pendingTrust is not null)
            {
                _knownHosts.Trust(
                    pendingTrust.Endpoint,
                    pendingTrust.Algorithm,
                    pendingTrust.FingerprintSha256);
            }

            Password.Clear();

            string label = string.IsNullOrWhiteSpace(profileName) ? host : profileName;
            slot.Tab.Header = $"{slot.BaseTitle} • {label}";
            slot.Status = $"Connected: {username}@{host}:{port}";

            UpdateActiveStatus();
            slot.Terminal.Focus();
        }
        catch (Exception ex)
        {
            Password.Clear();
            string message = hostKeyFailure ?? FriendlyConnectionError(ex);
            await DisconnectSlotAsync(slot, updateUi: true);

            MessageBox.Show(
                this,
                message,
                "SSH connection failed",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
    }

    private async void Disconnect_Click(object sender, RoutedEventArgs e)
    {
        await DisconnectSlotAsync(ActiveSlot, updateUi: true);
    }

    private async Task DisconnectSlotAsync(SessionSlot slot, bool updateUi)
    {
        var session = slot.Session;
        var client = slot.Client;
        var key = slot.PrivateKeyFile;

        slot.Session = null;
        slot.Client = null;
        slot.PrivateKeyFile = null;
        slot.Terminal.Session = null;

        if (session is not null)
        {
            try
            {
                await session.DisconnectAsync();
            }
            catch
            {
                // Disconnect is best-effort.
            }

            session.Dispose();
        }

        client?.Dispose();
        key?.Dispose();

        slot.Tab.Header = slot.BaseTitle;
        slot.Status = "Disconnected";

        if (updateUi && ReferenceEquals(slot, ActiveSlot))
            UpdateActiveStatus();
    }

    private void TerminalTabs_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_slots.Length == 0 || e.Source != TerminalTabs)
            return;

        UpdateActiveStatus();
    }

    private void UpdateActiveStatus()
    {
        if (_slots.Length == 0)
            return;

        StatusText.Text = $"{ActiveSlot.BaseTitle}: {ActiveSlot.Status}";
    }

    private void Copy_Click(object sender, RoutedEventArgs e)
    {
        var terminal = ActiveTerminal;
        if (TerminalControl.CopyCommand.CanExecute(null, terminal))
            TerminalControl.CopyCommand.Execute(null, terminal);
    }

    private void Paste_Click(object sender, RoutedEventArgs e)
    {
        var terminal = ActiveTerminal;
        if (TerminalControl.PasteCommand.CanExecute(null, terminal))
            TerminalControl.PasteCommand.Execute(null, terminal);

        terminal.Focus();
    }

    private void Terminal_PreviewMouseRightButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (sender is not TerminalControl terminal)
            return;

        // Right-click is always paste into the terminal that was clicked.
        if (TerminalControl.PasteCommand.CanExecute(null, terminal))
            TerminalControl.PasteCommand.Execute(null, terminal);

        e.Handled = true;
        terminal.Focus();
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (_slots.Length == 0)
            return;

        var focusedSlot = _slots
            .FirstOrDefault(slot => slot.Terminal.IsKeyboardFocusWithin);

        if (focusedSlot is null)
            return;

        if (e.Key == Key.C &&
            Keyboard.Modifiers.HasFlag(ModifierKeys.Control) &&
            !Keyboard.Modifiers.HasFlag(ModifierKeys.Shift))
        {
            // Selection already auto-copies on mouse-up. Plain Ctrl+C is therefore
            // unambiguous: always send ETX (0x03) to the active remote PTY.
            SendInterrupt(focusedSlot);
            e.Handled = true;
        }
    }

    private void StopCommand_Click(object sender, RoutedEventArgs e)
    {
        SendInterrupt(ActiveSlot);
    }

    private void SendInterrupt(SessionSlot slot)
    {
        if (slot.Session?.IsConnected != true)
        {
            slot.Status = "Not connected";
            if (ReferenceEquals(slot, ActiveSlot))
                UpdateActiveStatus();
            return;
        }

        slot.Session.Write([0x03]);
        slot.Status = "Interrupt sent (^C)";

        if (ReferenceEquals(slot, ActiveSlot))
        {
            UpdateActiveStatus();
            slot.Terminal.Focus();
        }
    }

    private void ClearBuffer_Click(object sender, RoutedEventArgs e)
    {
        var slot = ActiveSlot;
        if (slot.Session is null)
            return;

        int linesBefore = slot.Session.Buffer.ScrollbackCount;
        slot.Session.PurgeLocalScreenBuffer(slot.Terminal.ScrollbackLines);
        var trim = MemoryTrimmer.ReclaimAfterBufferPurge();

        long managedFreed = Math.Max(0, trim.ManagedBefore - trim.ManagedAfter);
        slot.Status =
            $"Buffer purged: {linesBefore:N0} lines; " +
            $"{managedFreed / 1024.0 / 1024.0:N1} MB managed memory released";

        UpdateActiveStatus();
        slot.Terminal.Focus();
    }

    private void SendCommand_Click(object sender, RoutedEventArgs e)
    {
        SendCommandBar();
    }

    private void CommandEntry_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Keyboard.Modifiers.HasFlag(ModifierKeys.Control))
        {
            SendCommandBar();
            e.Handled = true;
        }
    }

    private void SendCommandBar()
    {
        var slot = ActiveSlot;

        if (slot.Session?.IsConnected != true)
        {
            slot.Status = "Not connected";
            UpdateActiveStatus();
            return;
        }

        string command = CommandEntry.Text
            .Replace("\r\n", "\n", StringComparison.Ordinal)
            .Replace("\r", "\n", StringComparison.Ordinal)
            .TrimEnd();

        if (string.IsNullOrWhiteSpace(command))
            return;

        _history.Add(command);

        string payload = command.EndsWith('\n') ? command : command + "\n";
        slot.Session.Write(Encoding.UTF8.GetBytes(payload));

        CommandEntry.Clear();
        slot.Terminal.Focus();
    }

    private void ToggleHistory_Click(object sender, RoutedEventArgs e)
    {
        HistoryColumn.Width = HistoryColumn.Width.Value == 0
            ? new GridLength(330)
            : new GridLength(0);
    }

    private void LoadHistory_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryList.SelectedItem is not CommandHistoryEntry entry)
            return;

        CommandEntry.Text = entry.Text;
        CommandEntry.Focus();
        CommandEntry.CaretIndex = CommandEntry.Text.Length;
    }

    private void PinHistory_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryList.SelectedItem is not CommandHistoryEntry entry)
            return;

        _history.TogglePinned(entry);
        HistoryList.Items.Refresh();
    }

    private void DeleteHistory_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryList.SelectedItem is not CommandHistoryEntry entry)
            return;

        _history.Remove(entry);
    }

    private bool TryReadConnectionFields(
        out string name,
        out string host,
        out int port,
        out string username)
    {
        name = ProfileName.Text.Trim();
        host = HostName.Text.Trim();
        username = Username.Text.Trim();
        port = 0;

        if (string.IsNullOrWhiteSpace(name))
            name = host;

        if (string.IsNullOrWhiteSpace(host) ||
            string.IsNullOrWhiteSpace(username) ||
            !int.TryParse(Port.Text, out port) ||
            port is < 1 or > 65535)
        {
            MessageBox.Show(
                this,
                "Enter a valid host/IP, port and username.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return false;
        }

        return true;
    }

    private static string FriendlyConnectionError(Exception ex)
    {
        return ex switch
        {
            SshAuthenticationException => "SSH authentication failed.",
            SshConnectionException => $"SSH connection failed: {ex.Message}",
            _ => $"SSH connection failed: {ex.Message}"
        };
    }

    protected override void OnClosed(EventArgs e)
    {
        _history.Save();

        try
        {
            foreach (var slot in _slots)
            {
                slot.Session?.Dispose();
                slot.Client?.Dispose();
                slot.PrivateKeyFile?.Dispose();
            }
        }
        finally
        {
            base.OnClosed(e);
        }
    }
}

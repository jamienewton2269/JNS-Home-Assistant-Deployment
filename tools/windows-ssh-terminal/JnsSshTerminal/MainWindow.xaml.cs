using JnsSshTerminal.Models;
using JnsSshTerminal.Services;
using Microsoft.Win32;
using Renci.SshNet;
using Renci.SshNet.Common;
using System.Text;
using System.Windows;
using System.Windows.Input;
using VirtualTerminal;

namespace JnsSshTerminal;

public partial class MainWindow : Window
{
    private readonly ProfileStore _profileStore = new();
    private readonly CommandHistoryStore _history = new();
    private readonly KnownHostsStore _knownHosts = new();

    private List<HostProfile> _profiles = new();
    private JnsSecureShellSession? _session;
    private SshClient? _client;
    private PrivateKeyFile? _privateKeyFile;

    public MainWindow()
    {
        InitializeComponent();

        _profiles = _profileStore.Load();
        SavedHosts.ItemsSource = _profiles;

        _history.Load();
        HistoryList.ItemsSource = _history.Entries;
    }

    private void SavedHosts_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
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
        StatusText.Text = "Host saved";
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
        if (!TryReadConnectionFields(out _, out var host, out var port, out var username))
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

        await DisconnectInternalAsync();

        StatusText.Text = $"Connecting to {host}:{port}…";
        string endpoint = $"{host}:{port}";
        KnownHostEntry? pendingTrust = null;
        string? hostKeyFailure = null;

        try
        {
            if (!string.IsNullOrWhiteSpace(KeyFile.Text))
            {
                string path = KeyFile.Text.Trim();
                _privateKeyFile = string.IsNullOrEmpty(Password.Password)
                    ? new PrivateKeyFile(path)
                    : new PrivateKeyFile(path, Password.Password);

                _client = new SshClient(host, port, username, _privateKeyFile);
            }
            else
            {
                _client = new SshClient(host, port, username, Password.Password);
            }

            _client.HostKeyReceived += (_, args) =>
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

            _session = new JnsSecureShellSession(_client);
            Terminal.Session = _session;

            await _session.ConnectAsync();

            if (pendingTrust is not null)
            {
                _knownHosts.Trust(
                    pendingTrust.Endpoint,
                    pendingTrust.Algorithm,
                    pendingTrust.FingerprintSha256);
            }

            Password.Clear();
            StatusText.Text = $"Connected: {username}@{host}:{port}";
            Terminal.Focus();
        }
        catch (Exception ex)
        {
            Password.Clear();
            string message = hostKeyFailure ?? FriendlyConnectionError(ex);
            await DisconnectInternalAsync();

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
        await DisconnectInternalAsync();
    }

    private async Task DisconnectInternalAsync()
    {
        var session = _session;
        var client = _client;
        var key = _privateKeyFile;

        _session = null;
        _client = null;
        _privateKeyFile = null;
        Terminal.Session = null;

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

        StatusText.Text = "Disconnected";
    }

    private void Copy_Click(object sender, RoutedEventArgs e)
    {
        if (TerminalControl.CopyCommand.CanExecute(null, Terminal))
            TerminalControl.CopyCommand.Execute(null, Terminal);
    }

    private void Paste_Click(object sender, RoutedEventArgs e)
    {
        if (TerminalControl.PasteCommand.CanExecute(null, Terminal))
            TerminalControl.PasteCommand.Execute(null, Terminal);
        Terminal.Focus();
    }

    private void Terminal_MouseLeftButtonUp(object sender, MouseButtonEventArgs e)
    {
        // Selection is the copy gesture. No extra shortcut required.
        if (TerminalControl.CopyCommand.CanExecute(null, Terminal))
            TerminalControl.CopyCommand.Execute(null, Terminal);
    }

    private void Terminal_PreviewMouseRightButtonDown(object sender, MouseButtonEventArgs e)
    {
        // Right-click is always paste. Selection already copied on left mouse-up.
        if (TerminalControl.PasteCommand.CanExecute(null, Terminal))
            TerminalControl.PasteCommand.Execute(null, Terminal);

        e.Handled = true;
        Terminal.Focus();
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (!Terminal.IsKeyboardFocusWithin)
            return;

        if (e.Key == Key.C &&
            Keyboard.Modifiers.HasFlag(ModifierKeys.Control) &&
            !Keyboard.Modifiers.HasFlag(ModifierKeys.Shift) &&
            TerminalControl.CopyCommand.CanExecute(null, Terminal))
        {
            // With a selection Ctrl+C means copy. With no selection we do
            // nothing here and VirtualTerminal sends the normal terminal ^C.
            TerminalControl.CopyCommand.Execute(null, Terminal);
            e.Handled = true;
        }
    }

    private void ClearBuffer_Click(object sender, RoutedEventArgs e)
    {
        if (_session is null)
            return;

        int linesBefore = _session.Buffer.ScrollbackCount;
        _session.PurgeLocalScreenBuffer(Terminal.ScrollbackLines);
        var trim = MemoryTrimmer.ReclaimAfterBufferPurge();

        long managedFreed = Math.Max(0, trim.ManagedBefore - trim.ManagedAfter);
        StatusText.Text =
            $"Buffer purged: {linesBefore:N0} scrollback lines; " +
            $"{managedFreed / 1024.0 / 1024.0:N1} MB managed memory released";

        Terminal.Focus();
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
        if (_session?.IsConnected != true)
        {
            StatusText.Text = "Not connected";
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
        _session.Write(Encoding.UTF8.GetBytes(payload));

        CommandEntry.Clear();
        Terminal.Focus();
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
            _session?.Dispose();
            _client?.Dispose();
            _privateKeyFile?.Dispose();
        }
        finally
        {
            base.OnClosed(e);
        }
    }
}

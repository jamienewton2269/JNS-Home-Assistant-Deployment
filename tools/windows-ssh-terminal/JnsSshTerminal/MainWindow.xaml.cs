using JnsSshTerminal.Controls;
using JnsSshTerminal.Models;
using JnsSshTerminal.Services;
using Microsoft.Win32;
using Renci.SshNet;
using Renci.SshNet.Common;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Threading;
using VirtualTerminal;

namespace JnsSshTerminal;

public partial class MainWindow : Window
{
    private sealed class SessionSlot
    {
        public SessionSlot(string baseTitle, TabItem tab, JnsTerminalControl terminal, ScrollBar scrollBar)
        {
            BaseTitle = baseTitle;
            Tab = tab;
            Terminal = terminal;
            ScrollBar = scrollBar;
            Status = "Disconnected";
        }

        public string BaseTitle { get; }
        public TabItem Tab { get; }
        public JnsTerminalControl Terminal { get; }
        public ScrollBar ScrollBar { get; }

        public JnsSecureShellSession? Session { get; set; }
        public SshClient? Client { get; set; }
        public PrivateKeyFile? PrivateKeyFile { get; set; }
        public PasswordAuthenticationMethod? PasswordAuthentication { get; set; }

        public string Status { get; set; }
        public string Host { get; set; } = "";
        public int Port { get; set; } = 22;
        public string Username { get; set; } = "";
        public string Label { get; set; } = "";
        public string? KeyFilePath { get; set; }

        public bool Persistent { get; set; }
        public string? TmuxSessionName { get; set; }
    }

    private readonly ProfileStore _profileStore = new();
    private readonly CommandHistoryStore _history = new();
    private readonly KnownHostsStore _knownHosts = new();
    private readonly DetachedSessionStore _detachedStore = new();
    private readonly WindowsCredentialStore _credentialStore = new();
    private readonly SecureKeyStore _secureKeyStore = new();
    private readonly LocalDataWatchdog _localDataWatchdog = new();
    private readonly DispatcherTimer _maintenanceTimer = new();

    private List<HostProfile> _profiles = new();
    private List<DetachedSessionInfo> _detachedSessions = new();

    private readonly List<SessionSlot> _slots = [];
    private int _nextTerminalNumber = 2;

    private SessionSlot ActiveSlot =>
        _slots.FirstOrDefault(slot => ReferenceEquals(slot.Tab, TerminalTabs.SelectedItem))
        ?? _slots[0];

    private JnsTerminalControl ActiveTerminal => ActiveSlot.Terminal;

    public MainWindow()
    {
        InitializeComponent();

        RegisterSlot(new SessionSlot("Terminal 1", TerminalTab1, Terminal1, TerminalScrollBar1));
        RegisterSlot(new SessionSlot("Terminal 2", TerminalTab2, Terminal2, TerminalScrollBar2));

        _profiles = _profileStore.Load();
        SavedHosts.ItemsSource = _profiles;

        _detachedSessions = _detachedStore.Load();

        _history.Load();
        HistoryList.ItemsSource = _history.Entries;

        RunLocalMaintenance();
        RefreshDetachedSessions();
        UpdateCredentialStatus();

        _maintenanceTimer.Interval = TimeSpan.FromHours(24);
        _maintenanceTimer.Tick += (_, _) => RunLocalMaintenance();
        _maintenanceTimer.Start();

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
        UpdateCredentialStatus();
    }

    private void DetachedSessions_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (DetachedSessions.SelectedItem is not DetachedSessionInfo detached)
            return;

        ProfileName.Text = detached.Label;
        HostName.Text = detached.Host;
        Port.Text = detached.Port.ToString();
        Username.Text = detached.Username;

        var matchingProfile = _profiles.FirstOrDefault(p =>
            string.Equals(p.Host, detached.Host, StringComparison.OrdinalIgnoreCase) &&
            p.Port == detached.Port &&
            string.Equals(p.Username, detached.Username, StringComparison.OrdinalIgnoreCase));

        KeyFile.Text = matchingProfile?.KeyFile ?? detached.KeyFile ?? "";
        UpdateCredentialStatus();
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
            Filter = "SSH keys|*.jnskey;id_*;*.key;*.pem;*.ppk|JNS protected keys|*.jnskey|All files|*.*"
        };

        if (dialog.ShowDialog(this) == true)
            KeyFile.Text = dialog.FileName;
    }

    private void GenerateSecureKey_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var generated = _secureKeyStore.GenerateKey();
            KeyFile.Text = generated.PrivateKeyPath;
            Clipboard.SetText(generated.PublicKey);
            StatusText.Text = "Secure key generated; public key copied to clipboard";

            MessageBox.Show(
                this,
                $"A new JNS SSH key has been generated.\n\n" +
                $"Protected private key:\n{generated.PrivateKeyPath}\n\n" +
                $"Public key:\n{generated.PublicKeyPath}\n\n" +
                "The public key is already on the clipboard. Install it in the remote account's ~/.ssh/authorized_keys, then save this host profile.",
                "SSH key generated",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                $"Could not generate the SSH key: {ex.Message}",
                "SSH key generation failed",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
    }

    private void CopyPublicKey_Click(object sender, RoutedEventArgs e)
    {
        if (!_secureKeyStore.TryReadPublicKey(KeyFile.Text.Trim(), out string publicKey))
        {
            MessageBox.Show(
                this,
                "No matching public key was found for the selected private key.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        Clipboard.SetText(publicKey);
        StatusText.Text = "Public key copied to clipboard";
    }

    private async void Connect_Click(object sender, RoutedEventArgs e)
    {
        if (ActiveSlot.Session?.IsConnected == true)
        {
            MessageBox.Show(
                this,
                "The active terminal is already connected.\n\n" +
                "Use + New Terminal for another connection, or explicitly Detach & Close / Kill Remote Session first.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        await ConnectActiveAsync(null);
    }

    private async void ReattachDetached_Click(object sender, RoutedEventArgs e)
    {
        if (DetachedSessions.SelectedItem is not DetachedSessionInfo detached)
        {
            MessageBox.Show(
                this,
                "Select a persistent remote session first.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        if (detached.State == DetachedSessionState.Ended)
        {
            MessageBox.Show(
                this,
                "That remote tmux session has been confirmed ended and cannot be reattached.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        if (ActiveSlot.Session?.IsConnected == true)
            CreateTerminalSlot(select: true);

        ProfileName.Text = detached.Label;
        HostName.Text = detached.Host;
        Port.Text = detached.Port.ToString();
        Username.Text = detached.Username;

        if (string.IsNullOrWhiteSpace(KeyFile.Text))
        {
            var matchingProfile = _profiles.FirstOrDefault(p =>
                string.Equals(p.Host, detached.Host, StringComparison.OrdinalIgnoreCase) &&
                p.Port == detached.Port &&
                string.Equals(p.Username, detached.Username, StringComparison.OrdinalIgnoreCase));

            KeyFile.Text = matchingProfile?.KeyFile ?? detached.KeyFile ?? "";
        }

        await ConnectActiveAsync(detached);
    }

    private async Task ConnectActiveAsync(DetachedSessionInfo? reattach)
    {
        if (!TryReadConnectionFields(out var profileName, out var host, out var port, out var username))
            return;

        var slot = ActiveSlot;
        await CloseTransportAsync(slot);

        slot.Status = reattach is null
            ? $"Connecting to {host}:{port}…"
            : $"Reattaching {reattach.SessionName}…";
        UpdateActiveStatus();

        string endpoint = $"{host}:{port}";
        KnownHostEntry? pendingTrust = null;
        string? hostKeyFailure = null;
        byte[]? passwordUtf8 = null;
        bool typedPassword = false;

        try
        {
            string? keyPath = string.IsNullOrWhiteSpace(KeyFile.Text) ? null : KeyFile.Text.Trim();

            if (keyPath is not null)
            {
                if (_secureKeyStore.IsManagedKey(keyPath))
                {
                    slot.PrivateKeyFile = _secureKeyStore.OpenPrivateKey(keyPath);
                }
                else
                {
                    using var securePassphrase = Password.SecurePassword;
                    string? passphrase = securePassphrase.Length == 0
                        ? null
                        : SecureSecret.ToManagedString(securePassphrase);

                    slot.PrivateKeyFile = passphrase is null
                        ? new PrivateKeyFile(keyPath)
                        : new PrivateKeyFile(keyPath, passphrase);

                    passphrase = null;
                }

                slot.Client = new SshClient(host, port, username, slot.PrivateKeyFile);
            }
            else
            {
                using var securePassword = Password.SecurePassword;
                typedPassword = securePassword.Length > 0;

                passwordUtf8 = typedPassword
                    ? SecureSecret.ToUtf8Bytes(securePassword)
                    : _credentialStore.ReadPassword(host, port, username);

                if (passwordUtf8 is null || passwordUtf8.Length == 0)
                {
                    throw new InvalidOperationException(
                        "Enter the SSH account password, select a private key, or save the password securely for this host/user.");
                }

                slot.PasswordAuthentication = new PasswordAuthenticationMethod(username, passwordUtf8);
                slot.Client = new SshClient(new ConnectionInfo(
                    host,
                    port,
                    username,
                    slot.PasswordAuthentication));
            }

            slot.Host = host;
            slot.Port = port;
            slot.Username = username;
            slot.Label = string.IsNullOrWhiteSpace(profileName) ? host : profileName;
            slot.KeyFilePath = keyPath;

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
            slot.Session.BufferUpdated += (_, _) =>
                Dispatcher.BeginInvoke(() => UpdateScrollBar(slot));

            await slot.Session.ConnectAsync();

            if (keyPath is null &&
                typedPassword &&
                RememberPassword.IsChecked == true &&
                passwordUtf8 is { Length: > 0 })
            {
                _credentialStore.SavePassword(host, port, username, passwordUtf8);
            }

            if (passwordUtf8 is not null)
            {
                CryptographicOperations.ZeroMemory(passwordUtf8);
                passwordUtf8 = null;
            }

            UpdateCredentialStatus();

            bool tmuxAvailable = await RemoteCommandSucceedsAsync(
                slot.Client,
                "command -v tmux >/dev/null 2>&1");

            if (reattach is not null)
            {
                if (!tmuxAvailable)
                {
                    throw new InvalidOperationException(
                        "This host no longer has tmux available, so the detached terminal cannot be reattached.");
                }

                bool exists = await RemoteCommandSucceedsAsync(
                    slot.Client,
                    $"tmux has-session -t {ShellQuote(reattach.SessionName)} 2>/dev/null");

                if (!exists)
                {
                    MarkSessionEnded(
                        reattach.Host,
                        reattach.Port,
                        reattach.Username,
                        reattach.SessionName);

                    throw new InvalidOperationException(
                        "The persistent tmux session no longer exists on the remote host. It has been marked Ended in the local registry.");
                }

                slot.Persistent = true;
                slot.TmuxSessionName = reattach.SessionName;
                slot.Session.Write(Encoding.UTF8.GetBytes(
                    $"tmux attach-session -t {ShellQuote(reattach.SessionName)}\n"));

                SaveDetachedRecord(slot, DetachedSessionState.RunningAttached);
            }
            else if (tmuxAvailable)
            {
                slot.Persistent = true;
                slot.TmuxSessionName = GenerateTmuxSessionName();

                var createTmux = await RunRemoteCommandAsync(
                    slot.Client,
                    $"tmux new-session -d -s {ShellQuote(slot.TmuxSessionName)}");

                if (createTmux.ExitStatus != 0)
                    throw new InvalidOperationException($"tmux could not create the persistent session: {createTmux.Error}");

                slot.Session.Write(Encoding.UTF8.GetBytes(
                    $"tmux attach-session -t {ShellQuote(slot.TmuxSessionName)}\n"));

                SaveDetachedRecord(slot, DetachedSessionState.RunningAttached);
            }
            else
            {
                slot.Persistent = false;
                slot.TmuxSessionName = null;
            }

            slot.Terminal.Session = slot.Session;

            if (pendingTrust is not null)
            {
                _knownHosts.Trust(
                    pendingTrust.Endpoint,
                    pendingTrust.Algorithm,
                    pendingTrust.FingerprintSha256);
            }

            Password.Clear();

            slot.Tab.Header = $"{slot.BaseTitle} • {slot.Label}";
            slot.Status = slot.Persistent
                ? $"Connected: {username}@{host}:{port} • persistent tmux"
                : $"Connected: {username}@{host}:{port} • tmux unavailable";

            UpdateActiveStatus();
            slot.Terminal.Focus();
        }
        catch (Exception ex)
        {
            Password.Clear();
            string message = hostKeyFailure ?? FriendlyConnectionError(ex);
            await CloseTransportAsync(slot);
            ResetSlot(slot);

            MessageBox.Show(
                this,
                message,
                "SSH connection failed",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        finally
        {
            if (passwordUtf8 is not null)
                CryptographicOperations.ZeroMemory(passwordUtf8);
        }
    }

    private void NewTerminal_Click(object sender, RoutedEventArgs e)
    {
        CreateTerminalSlot(select: true);
    }

    private SessionSlot CreateTerminalSlot(bool select)
    {
        int number = ++_nextTerminalNumber;
        string title = $"Terminal {number}";

        var terminal = new JnsTerminalControl
        {
            AllowDirectInput = true,
            ScrollDownVisible = true,
            ScrollbackLines = 3000,
            Background = Terminal1.Background,
            Foreground = Terminal1.Foreground,
            FontFamily = Terminal1.FontFamily,
            FontSize = Terminal1.FontSize
        };
        terminal.PreviewMouseRightButtonDown += Terminal_PreviewMouseRightButtonDown;

        var scrollBar = new ScrollBar
        {
            Orientation = Orientation.Vertical,
            Minimum = 0,
            Maximum = 0,
            SmallChange = 3,
            LargeChange = 25,
            Width = 28,
            Style = (Style)FindResource("TerminalScrollBarStyle")
        };
        scrollBar.ValueChanged += TerminalScrollBar_ValueChanged;

        var host = new Grid();
        host.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        host.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(28) });

        Grid.SetColumn(terminal, 0);
        Grid.SetColumn(scrollBar, 1);
        host.Children.Add(terminal);
        host.Children.Add(scrollBar);

        var tab = new TabItem
        {
            Header = title,
            Content = host
        };

        var slot = new SessionSlot(title, tab, terminal, scrollBar);
        RegisterSlot(slot);
        TerminalTabs.Items.Add(tab);

        if (select)
            TerminalTabs.SelectedItem = tab;

        UpdateActiveStatus();
        return slot;
    }

    private void RegisterSlot(SessionSlot slot)
    {
        _slots.Add(slot);
        slot.Terminal.ScrollPositionChanged += (_, _) => UpdateScrollBar(slot);
        UpdateScrollBar(slot);
    }

    private async void DetachClose_Click(object sender, RoutedEventArgs e)
    {
        var slot = ActiveSlot;

        if (slot.Session?.IsConnected != true)
        {
            RemoveSlot(slot);
            return;
        }

        if (!slot.Persistent || string.IsNullOrWhiteSpace(slot.TmuxSessionName))
        {
            MessageBox.Show(
                this,
                "This remote host does not have a tmux-backed persistent session.\n\n" +
                "Closing this view would terminate its SSH PTY, so it has not been closed. " +
                "Use Kill Remote Session if you intentionally want to end it.",
                "Cannot safely detach",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
            return;
        }

        try
        {
            await RunRemoteCommandAsync(
                slot.Client!,
                $"tmux detach-client -s {ShellQuote(slot.TmuxSessionName)} 2>/dev/null || true");

            SaveDetachedRecord(slot, DetachedSessionState.RunningDetached);
            await CloseTransportAsync(slot);
            RemoveSlot(slot);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                $"Could not detach the remote terminal safely: {ex.Message}",
                "Detach failed",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
    }

    private async void KillSession_Click(object sender, RoutedEventArgs e)
    {
        var slot = ActiveSlot;

        if (slot.Session?.IsConnected != true)
        {
            RemoveSlot(slot);
            return;
        }

        var answer = MessageBox.Show(
            this,
            "Terminate the remote terminal session and close this tab?\n\n" +
            "Any foreground command running inside this terminal will be terminated. " +
            "This cannot be reattached afterwards.",
            "Kill remote session",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);

        if (answer != MessageBoxResult.Yes)
            return;

        try
        {
            if (slot.Persistent && !string.IsNullOrWhiteSpace(slot.TmuxSessionName))
            {
                await RunRemoteCommandAsync(
                    slot.Client!,
                    $"tmux kill-session -t {ShellQuote(slot.TmuxSessionName)} 2>/dev/null || true");

                MarkSessionEnded(
                    slot.Host,
                    slot.Port,
                    slot.Username,
                    slot.TmuxSessionName);
            }

            await CloseTransportAsync(slot);
            RemoveSlot(slot);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                $"Remote session termination reported an error: {ex.Message}",
                "Kill remote session",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
    }

    private async Task CloseTransportAsync(SessionSlot slot)
    {
        var session = slot.Session;
        var client = slot.Client;
        var key = slot.PrivateKeyFile;
        var passwordAuthentication = slot.PasswordAuthentication;

        slot.Session = null;
        slot.Client = null;
        slot.PrivateKeyFile = null;
        slot.PasswordAuthentication = null;
        slot.Terminal.Session = null;
        slot.Terminal.ResetTrackedScroll();
        UpdateScrollBar(slot);

        if (session is not null)
        {
            try
            {
                await session.DisconnectAsync();
            }
            catch
            {
                // Transport shutdown is best-effort.
            }

            session.Dispose();
        }

        client?.Dispose();
        passwordAuthentication?.Dispose();
        key?.Dispose();
    }

    private void RemoveSlot(SessionSlot slot)
    {
        int index = TerminalTabs.Items.IndexOf(slot.Tab);

        TerminalTabs.Items.Remove(slot.Tab);
        _slots.Remove(slot);

        if (_slots.Count == 0)
        {
            CreateTerminalSlot(select: true);
            return;
        }

        int nextIndex = Math.Clamp(index, 0, TerminalTabs.Items.Count - 1);
        TerminalTabs.SelectedIndex = nextIndex;
        UpdateActiveStatus();
        ActiveTerminal.Focus();
    }

    private void ResetSlot(SessionSlot slot)
    {
        slot.Tab.Header = slot.BaseTitle;
        slot.Status = "Disconnected";
        slot.Persistent = false;
        slot.TmuxSessionName = null;
        slot.Host = "";
        slot.Username = "";
        slot.Label = "";
        slot.KeyFilePath = null;

        if (ReferenceEquals(slot, ActiveSlot))
            UpdateActiveStatus();
    }

    private void SaveDetachedRecord(
        SessionSlot slot,
        DetachedSessionState state = DetachedSessionState.RunningDetached)
    {
        if (!slot.Persistent || string.IsNullOrWhiteSpace(slot.TmuxSessionName))
            return;

        DateTime now = DateTime.UtcNow;
        var existing = _detachedSessions.FirstOrDefault(item =>
            SameSession(item, slot.Host, slot.Port, slot.Username, slot.TmuxSessionName));

        var record = existing ?? new DetachedSessionInfo
        {
            SessionName = slot.TmuxSessionName,
            Host = slot.Host,
            Port = slot.Port,
            Username = slot.Username,
            FirstRecordedUtc = now
        };

        record.Label = string.IsNullOrWhiteSpace(slot.Label) ? slot.Host : slot.Label;
        record.KeyFile = slot.KeyFilePath;
        record.State = state;
        record.LastSeenUtc = now;
        record.LastCheckedUtc = now;
        record.ConfirmedEndedUtc = null;

        if (existing is null)
            _detachedSessions.Add(record);

        _detachedStore.Save(_detachedSessions);
        RefreshDetachedSessions(record.SessionName);
    }

    private void MarkSessionEnded(
        string host,
        int port,
        string username,
        string sessionName)
    {
        DateTime now = DateTime.UtcNow;

        foreach (var item in _detachedSessions.Where(item =>
                     SameSession(item, host, port, username, sessionName)))
        {
            item.State = DetachedSessionState.Ended;
            item.LastCheckedUtc = now;
            item.ConfirmedEndedUtc ??= now;
        }

        _detachedStore.Save(_detachedSessions);
        RefreshDetachedSessions(sessionName);
    }

    private void RefreshDetachedSessions(string? selectSessionName = null)
    {
        _detachedSessions = _detachedSessions
            .OrderBy(item => item.State == DetachedSessionState.Ended ? 1 : 0)
            .ThenByDescending(item => item.LastSeenUtc ?? item.FirstRecordedUtc)
            .ToList();

        DetachedSessions.ItemsSource = null;
        DetachedSessions.ItemsSource = _detachedSessions;

        if (selectSessionName is not null)
        {
            DetachedSessions.SelectedItem = _detachedSessions.FirstOrDefault(item =>
                string.Equals(item.SessionName, selectSessionName, StringComparison.Ordinal));
        }
    }

    private async void RefreshSessions_Click(object sender, RoutedEventArgs e)
    {
        if (!TryReadConnectionFields(out var label, out var host, out var port, out var username))
            return;

        ProbeConnection? probe = null;

        try
        {
            probe = await OpenProbeConnectionAsync(host, port, username);

            bool tmuxAvailable = await RemoteCommandSucceedsAsync(
                probe.Client,
                "command -v tmux >/dev/null 2>&1");

            if (!tmuxAvailable)
            {
                MarkHostSessionsEnded(host, port, username);

                MessageBox.Show(
                    this,
                    "The host is reachable, but tmux is not available. Previously registered JNS tmux sessions for this account are marked Ended.",
                    "Session refresh",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information);
                return;
            }

            var command = await RunRemoteCommandAsync(
                probe.Client,
                "tmux list-sessions -F '#{session_name}\\t#{session_created}\\t#{session_attached}' 2>/dev/null || true");

            ReconcileRemoteSessions(
                label,
                host,
                port,
                username,
                string.IsNullOrWhiteSpace(KeyFile.Text) ? null : KeyFile.Text.Trim(),
                command.Result);

            StatusText.Text = $"Session registry refreshed: {username}@{host}:{port}";
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                FriendlyConnectionError(ex),
                "Session refresh failed",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        finally
        {
            probe?.Dispose();
            Password.Clear();
            UpdateCredentialStatus();
        }
    }

    private void RemoveEndedSession_Click(object sender, RoutedEventArgs e)
    {
        if (DetachedSessions.SelectedItem is not DetachedSessionInfo item ||
            item.State != DetachedSessionState.Ended)
        {
            MessageBox.Show(
                this,
                "Select a session marked ENDED first.",
                "JNS SSH",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        _detachedSessions.Remove(item);
        _detachedStore.Save(_detachedSessions);
        RefreshDetachedSessions();
    }

    private void ReconcileRemoteSessions(
        string label,
        string host,
        int port,
        string username,
        string? keyFile,
        string output)
    {
        DateTime now = DateTime.UtcNow;
        var remote = new Dictionary<string, (DateTime? CreatedUtc, bool Attached)>(
            StringComparer.Ordinal);

        foreach (string line in output.Split(
                     ['\r', '\n'],
                     StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            string[] parts = line.Split('\t');

            if (parts.Length < 3 ||
                !parts[0].StartsWith("jns-", StringComparison.Ordinal))
                continue;

            DateTime? createdUtc = null;
            if (long.TryParse(parts[1], out long epoch))
                createdUtc = DateTimeOffset.FromUnixTimeSeconds(epoch).UtcDateTime;

            bool attached =
                int.TryParse(parts[2], out int attachedCount) &&
                attachedCount > 0;

            remote[parts[0]] = (createdUtc, attached);
        }

        foreach (var local in _detachedSessions.Where(item =>
                     SameHost(item, host, port, username)))
        {
            local.LastCheckedUtc = now;

            if (remote.Remove(local.SessionName, out var remoteState))
            {
                local.State = remoteState.Attached
                    ? DetachedSessionState.RunningAttached
                    : DetachedSessionState.RunningDetached;
                local.LastSeenUtc = now;
                local.ConfirmedEndedUtc = null;
                local.RemoteCreatedUtc ??= remoteState.CreatedUtc;
            }
            else
            {
                local.State = DetachedSessionState.Ended;
                local.ConfirmedEndedUtc ??= now;
            }
        }

        foreach (var pair in remote)
        {
            _detachedSessions.Add(new DetachedSessionInfo
            {
                SessionName = pair.Key,
                Label = string.IsNullOrWhiteSpace(label) ? $"{host} (discovered)" : label,
                Host = host,
                Port = port,
                Username = username,
                KeyFile = keyFile,
                FirstRecordedUtc = now,
                RemoteCreatedUtc = pair.Value.CreatedUtc,
                LastSeenUtc = now,
                LastCheckedUtc = now,
                State = pair.Value.Attached
                    ? DetachedSessionState.RunningAttached
                    : DetachedSessionState.RunningDetached
            });
        }

        _detachedStore.Save(_detachedSessions);
        RefreshDetachedSessions();
        RunLocalMaintenance();
    }

    private void MarkHostSessionsEnded(string host, int port, string username)
    {
        DateTime now = DateTime.UtcNow;

        foreach (var item in _detachedSessions.Where(item =>
                     SameHost(item, host, port, username)))
        {
            item.State = DetachedSessionState.Ended;
            item.LastCheckedUtc = now;
            item.ConfirmedEndedUtc ??= now;
        }

        _detachedStore.Save(_detachedSessions);
        RefreshDetachedSessions();
    }

    private static bool SameHost(
        DetachedSessionInfo item,
        string host,
        int port,
        string username) =>
        string.Equals(item.Host, host, StringComparison.OrdinalIgnoreCase) &&
        item.Port == port &&
        string.Equals(item.Username, username, StringComparison.OrdinalIgnoreCase);

    private static bool SameSession(
        DetachedSessionInfo item,
        string host,
        int port,
        string username,
        string sessionName) =>
        SameHost(item, host, port, username) &&
        string.Equals(item.SessionName, sessionName, StringComparison.Ordinal);

    private void ForgetSavedPassword_Click(object sender, RoutedEventArgs e)
    {
        if (!TryReadConnectionFields(out _, out var host, out var port, out var username))
            return;

        _credentialStore.DeletePassword(host, port, username);
        RememberPassword.IsChecked = false;
        UpdateCredentialStatus();
        StatusText.Text = $"Saved password removed: {username}@{host}:{port}";
    }

    private void UpdateCredentialStatus()
    {
        string host = HostName.Text.Trim();
        string username = Username.Text.Trim();

        if (!int.TryParse(Port.Text, out int port) ||
            string.IsNullOrWhiteSpace(host) ||
            string.IsNullOrWhiteSpace(username))
        {
            CredentialStatusText.Text = "Saved password status: select a host";
            return;
        }

        CredentialStatusText.Text = _credentialStore.HasPassword(host, port, username)
            ? "Saved password available in Windows Credential Manager"
            : "No saved SSH account password for this host/user";
    }

    private async Task<ProbeConnection> OpenProbeConnectionAsync(string host, int port, string username)
    {
        byte[]? passwordUtf8 = null;
        PrivateKeyFile? keyFile = null;
        PasswordAuthenticationMethod? passwordAuthentication = null;
        SshClient? client = null;
        bool typedPassword = false;

        string endpoint = $"{host}:{port}";
        KnownHostEntry? pendingTrust = null;
        string? hostKeyFailure = null;

        try
        {
            string? keyPath = string.IsNullOrWhiteSpace(KeyFile.Text) ? null : KeyFile.Text.Trim();

            if (keyPath is not null)
            {
                if (_secureKeyStore.IsManagedKey(keyPath))
                    keyFile = _secureKeyStore.OpenPrivateKey(keyPath);
                else
                {
                    using var securePassphrase = Password.SecurePassword;
                    string? passphrase = securePassphrase.Length == 0
                        ? null
                        : SecureSecret.ToManagedString(securePassphrase);
                    keyFile = passphrase is null
                        ? new PrivateKeyFile(keyPath)
                        : new PrivateKeyFile(keyPath, passphrase);
                    passphrase = null;
                }

                client = new SshClient(host, port, username, keyFile);
            }
            else
            {
                using var securePassword = Password.SecurePassword;
                typedPassword = securePassword.Length > 0;
                passwordUtf8 = typedPassword
                    ? SecureSecret.ToUtf8Bytes(securePassword)
                    : _credentialStore.ReadPassword(host, port, username);

                if (passwordUtf8 is null || passwordUtf8.Length == 0)
                    throw new InvalidOperationException("Enter the SSH account password, select a private key, or save the password securely for this host/user.");

                passwordAuthentication = new PasswordAuthenticationMethod(username, passwordUtf8);
                client = new SshClient(new ConnectionInfo(host, port, username, passwordAuthentication));
            }

            client.HostKeyReceived += (_, args) =>
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
                        hostKeyFailure =
                            $"HOST KEY CHANGED for {endpoint}.\n\n" +
                            $"Expected SHA256:{known.FingerprintSha256}\n" +
                            $"Received SHA256:{fingerprint}\n\nConnection rejected.";
                    return;
                }

                bool accepted = Dispatcher.Invoke(() =>
                    MessageBox.Show(
                        this,
                        $"First connection to {endpoint}.\n\nAlgorithm: {args.HostKeyName}\nSHA256:{fingerprint}\n\nTrust this host key?",
                        "Verify SSH host key",
                        MessageBoxButton.YesNo,
                        MessageBoxImage.Question) == MessageBoxResult.Yes);
                args.CanTrust = accepted;
                if (accepted)
                    pendingTrust = new KnownHostEntry
                    {
                        Endpoint = endpoint,
                        Algorithm = args.HostKeyName,
                        FingerprintSha256 = fingerprint
                    };
            };

            await Task.Run(client.Connect);

            if (hostKeyFailure is not null)
                throw new InvalidOperationException(hostKeyFailure);

            if (pendingTrust is not null)
                _knownHosts.Trust(pendingTrust.Endpoint, pendingTrust.Algorithm, pendingTrust.FingerprintSha256);

            if (keyPath is null &&
                typedPassword &&
                RememberPassword.IsChecked == true &&
                passwordUtf8 is { Length: > 0 })
                _credentialStore.SavePassword(host, port, username, passwordUtf8);

            if (passwordUtf8 is not null)
            {
                CryptographicOperations.ZeroMemory(passwordUtf8);
                passwordUtf8 = null;
            }

            return new ProbeConnection(client, keyFile, passwordAuthentication);
        }
        catch
        {
            if (passwordUtf8 is not null)
                CryptographicOperations.ZeroMemory(passwordUtf8);
            client?.Dispose();
            passwordAuthentication?.Dispose();
            keyFile?.Dispose();
            if (hostKeyFailure is not null)
                throw new InvalidOperationException(hostKeyFailure);
            throw;
        }
    }

    private sealed class ProbeConnection : IDisposable
    {
        public ProbeConnection(SshClient client, PrivateKeyFile? keyFile, PasswordAuthenticationMethod? passwordAuthentication)
        {
            Client = client;
            KeyFile = keyFile;
            PasswordAuthentication = passwordAuthentication;
        }

        public SshClient Client { get; }
        private PrivateKeyFile? KeyFile { get; }
        private PasswordAuthenticationMethod? PasswordAuthentication { get; }

        public void Dispose()
        {
            Client.Dispose();
            PasswordAuthentication?.Dispose();
            KeyFile?.Dispose();
        }
    }

    private void RunLocalMaintenance()
    {
        _localDataWatchdog.CleanupTransientFiles();
        _history.RunMaintenance();
        _detachedSessions = _localDataWatchdog.PruneSessionRegistry(_detachedSessions).ToList();
        _detachedStore.Save(_detachedSessions);
        RefreshDetachedSessions();
    }

    private void TerminalTabs_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_slots.Count == 0 || e.Source != TerminalTabs)
            return;

        UpdateActiveStatus();
        UpdateScrollBar(ActiveSlot);
    }

    private void TerminalScrollBar_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (sender is not ScrollBar scrollBar)
            return;

        var slot = _slots.FirstOrDefault(candidate => ReferenceEquals(candidate.ScrollBar, scrollBar));
        if (slot is null || scrollBar.Tag as string == "sync")
            return;

        int max = slot.Session?.Buffer.ScrollbackCount ?? 0;
        int targetOffset = Math.Clamp(
            max - (int)Math.Round(scrollBar.Value),
            0,
            max);

        slot.Terminal.ScrollToOffset(targetOffset);
        UpdateScrollBar(slot);
        slot.Terminal.Focus();
    }

    private void UpdateScrollBar(SessionSlot slot)
    {
        int max = slot.Session?.Buffer.ScrollbackCount ?? 0;
        int offset = Math.Clamp(slot.Terminal.ScrollOffset, 0, max);

        slot.ScrollBar.Tag = "sync";
        try
        {
            slot.ScrollBar.Maximum = max;
            slot.ScrollBar.ViewportSize = Math.Max(1, slot.Terminal.ActualHeight / Math.Max(1, slot.Terminal.FontSize));
            slot.ScrollBar.Value = Math.Clamp(max - offset, 0, max);
            slot.ScrollBar.IsEnabled = max > 0;
        }
        finally
        {
            slot.ScrollBar.Tag = null;
        }
    }

    private void UpdateActiveStatus()
    {
        if (_slots.Count == 0)
            return;

        StatusText.Text = $"{ActiveSlot.BaseTitle}: {ActiveSlot.Status}";
    }

    private void SelectAll_Click(object sender, RoutedEventArgs e)
    {
        var terminal = ActiveTerminal;
        if (TerminalControl.SelectAllCommand.CanExecute(null, terminal))
            TerminalControl.SelectAllCommand.Execute(null, terminal);

        terminal.Focus();
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

        if (TerminalControl.PasteCommand.CanExecute(null, terminal))
            TerminalControl.PasteCommand.Execute(null, terminal);

        e.Handled = true;
        terminal.Focus();
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (_slots.Count == 0)
            return;

        var terminal = _slots
            .Select(slot => slot.Terminal)
            .FirstOrDefault(candidate => candidate.IsKeyboardFocusWithin);

        if (terminal is null)
            return;

        if (e.Key == Key.C &&
            Keyboard.Modifiers.HasFlag(ModifierKeys.Control) &&
            !Keyboard.Modifiers.HasFlag(ModifierKeys.Shift))
        {
            if (TerminalControl.CopyCommand.CanExecute(null, terminal))
                TerminalControl.CopyCommand.Execute(null, terminal);

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
        slot.Terminal.ClearLocalSelection();
        slot.Session.PurgeLocalScreenBuffer(slot.Terminal.ScrollbackLines);
        slot.Terminal.ResetTrackedScroll();
        UpdateScrollBar(slot);

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

    private static string GenerateTmuxSessionName() =>
        $"jns-{DateTime.UtcNow:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}"[..32];

    private static string ShellQuote(string value) =>
        "'" + value.Replace("'", "'\"'\"'", StringComparison.Ordinal) + "'";

    private static async Task<bool> RemoteCommandSucceedsAsync(SshClient client, string command)
    {
        var result = await RunRemoteCommandAsync(client, command);
        return result.ExitStatus == 0;
    }

    private static Task<SshCommand> RunRemoteCommandAsync(SshClient client, string command) =>
        Task.Run(() => client.RunCommand(command));

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

        foreach (var slot in _slots)
        {
            try
            {
                if (slot.Persistent &&
                    slot.Session?.IsConnected == true &&
                    !string.IsNullOrWhiteSpace(slot.TmuxSessionName))
                {
                    SaveDetachedRecord(slot, DetachedSessionState.RunningDetached);
                }
            }
            catch
            {
                // Do not block application shutdown if persistence metadata fails.
            }

            slot.Session?.Dispose();
            slot.Client?.Dispose();
            slot.PasswordAuthentication?.Dispose();
            slot.PrivateKeyFile?.Dispose();
        }

        _maintenanceTimer.Stop();
        base.OnClosed(e);
    }
}

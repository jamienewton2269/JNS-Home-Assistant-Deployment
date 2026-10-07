using System.Diagnostics;
using System.Runtime.InteropServices;

namespace JnsSshTerminal.Services;

internal readonly record struct MemoryTrimResult(
    long ManagedBefore,
    long ManagedAfter,
    long WorkingSetBefore,
    long WorkingSetAfter);

internal static class MemoryTrimmer
{
    [DllImport("psapi.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EmptyWorkingSet(IntPtr process);

    public static MemoryTrimResult ReclaimAfterBufferPurge()
    {
        long managedBefore = GC.GetTotalMemory(false);
        using var processBefore = Process.GetCurrentProcess();
        long workingSetBefore = processBefore.WorkingSet64;

        GC.Collect(GC.MaxGeneration, GCCollectionMode.Forced, blocking: true, compacting: true);
        GC.WaitForPendingFinalizers();
        GC.Collect(GC.MaxGeneration, GCCollectionMode.Forced, blocking: true, compacting: true);

        try
        {
            using var process = Process.GetCurrentProcess();
            _ = EmptyWorkingSet(process.Handle);
        }
        catch
        {
            // Best effort. The buffer references have already been removed.
        }

        long managedAfter = GC.GetTotalMemory(false);
        using var processAfter = Process.GetCurrentProcess();
        long workingSetAfter = processAfter.WorkingSet64;

        return new MemoryTrimResult(
            managedBefore,
            managedAfter,
            workingSetBefore,
            workingSetAfter);
    }
}

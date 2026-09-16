// What a copy actually costs, on a real NMOS core with Disk II timing.
// Disposable images only (argv[2] boot, argv[3] target).
//
// Why measure cycles: at 1 MHz a Disk II revolution is about 200 000
// cycles. Every sector RWTS misses costs one whole revolution, and every
// change of drive costs a seek on top. So the interesting number is not
// how much work the code does but how many revolutions it waits through.
//
// Per-call detail: a debug hook watches DOS's RWTS entry at $03D9 during the
// writing phase and timestamps every entry and return. The hook costs no
// emulated cycles (M6502::run just swaps loops), so the totals below stay
// comparable with the runs that predate it.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

static std::string screen(Memory& m) {
    std::string s;
    for (int y = 0; y < 24; ++y) {
        for (int x = 0; x < 40; ++x) {
            unsigned char c = m.data()[0x400 + (y & 7) * 128 + (y >> 3) * 40 + x] & 127;
            if (c < 32) c += 64;
            s += c;
        }
        s += '\n';
    }
    return s;
}

static std::string mini_files(const char* suffix) {
    // the boot disk's file count, from the driver: the shipped disk may carry more than the four built files
    const char* n=getenv("MINI_FILES"); return std::string(n?n:"4")+suffix;
}
static void run(M6502& c, long cycles) { for (long n = 0; n < cycles;) n += c.run(1024); }

static void expect(Memory& m, const char* needle) {
    if (screen(m).find(needle) == std::string::npos) {
        fprintf(stderr, "missing %s\n%s", needle, screen(m).c_str());
        std::exit(1);
    }
}

// Cycles from the keystroke until `needle` shows up.
static long timed(Memory& m, M6502& cpu, const char* keys, const char* needle) {
    m.pasteRawKeys(keys, strlen(keys));
    long n = 0;
    while (n < 900000000L && screen(m).find(needle) == std::string::npos) n += cpu.run(1024);
    if (screen(m).find(needle) == std::string::npos) {
        fprintf(stderr, "never reached %s\n%s", needle, screen(m).c_str());
        std::exit(1);
    }
    return n;
}

// One RWTS call: what the IOB asked for, and when the call started and ended.
struct Call {
    int cmd, drive, track, sector;
    unsigned long long enter, leave;
};

// RWTS is entered through the JMP at $03D9 with the IOB address in A (high)
// and Y (low); the call is over when the stack pointer climbs back above its
// value at the entry point, i.e. when RWTS's RTS has popped the caller's
// return address.
class RwtsTracer : public M6502DebugHook {
public:
    RwtsTracer(Memory& m, M6502& c) : mem_(m), cpu_(c) {}
    bool armed = false;
    std::vector<Call> calls;

    bool onInstruction(uint16_t pc) override {
        if (!armed) return false;
        if (!inside_) {
            if (pc == 0x03D9) {
                unsigned short iob =
                    (unsigned short)((cpu_.getAccumulator() << 8) | cpu_.getYRegister());
                cur_.drive = mem_.data()[iob + 2];
                cur_.track = mem_.data()[iob + 4];
                cur_.sector = mem_.data()[iob + 5];
                cur_.cmd = mem_.data()[iob + 12];
                cur_.enter = mem_.getCycleCounter();
                sp_ = cpu_.getStackPointer();
                inside_ = true;
            }
        } else if (cpu_.getStackPointer() > sp_) {
            cur_.leave = mem_.getCycleCounter();
            calls.push_back(cur_);
            inside_ = false;
        }
        return false;
    }

private:
    Memory& mem_;
    M6502& cpu_;
    bool inside_ = false;
    unsigned char sp_ = 0;
    Call cur_{};
};

int main(int argc, char** argv) {
    assert(argc == 4);
    Memory m;
    m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1]) + "/roms/apple2p.rom").c_str()));
    auto card = std::make_unique<DiskIICard>();
    auto* d = card.get();
    assert(d->loadBootRom(std::string(argv[1]) + "/roms/disk2.rom"));
    assert(d->insertDisk(0, argv[2]));
    assert(d->insertDisk(1, argv[3]));
    d->setWriteBackEnabled(true);
    m.slotBus().plug(6, std::move(card));
    M6502 cpu(&m);
    m.setCpu(&cpu);
    cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam();
    m.resetSoftSwitches();
    m.slotBus().reset();
    cpu.hardReset();
    cpu.setProgramCounter(0xc600);
    run(cpu, 120000000);
    expect(m, mini_files(" FILES").c_str());

    // The catalog path on its own. The file count of the active panel
    // tells the two disks apart: 4 files on boot, 1 on the target. The
    // first switch pays the motor spin-up, the later ones do not.
    long to_target = timed(m, cpu, "/", "1 FILES");
    long warm[6];
    for (int i = 0; i < 3; ++i) {
        warm[i * 2] = timed(m, cpu, "/", mini_files(" FILES").c_str());
        warm[i * 2 + 1] = timed(m, cpu, "/", "1 FILES");
    }
    m.pasteRawKeys("/", 1);
    run(cpu, 12000000);
    expect(m, mini_files(" FILES").c_str());

    // Then the copy of A2FC, the largest file on the boot disk.
    m.pasteRawKeys("\t/\tK", 4);
    run(cpu, 24000000);
    expect(m, "A2FC");
    long prepare = timed(m, cpu, "C", "CANCEL");
    expect(m, "COPY ");
    expect(m, "KEEP.DST");
    RwtsTracer tracer(m, cpu);
    cpu.setDebugHook(&tracer);
    tracer.armed = true;
    long execute = timed(m, cpu, "Y", "COPIED");
    tracer.armed = false;
    cpu.setDebugHook(nullptr);

    printf("catalog, first switch to drive 2: %ld cycles\n", to_target);
    printf("catalog, warm switches:           %ld %ld %ld %ld %ld %ld cycles\n",
           warm[0], warm[1], warm[2], warm[3], warm[4], warm[5]);
    printf("copy A2FC, prepare:          %ld cycles\n", prepare);
    printf("copy A2FC, writing phase:    %ld cycles\n", execute);
    printf("copy A2FC, total:            %ld cycles = %.1f s at 1 MHz\n",
           prepare + execute, (prepare + execute) / 1.0e6);

    // Per-call breakdown of the writing phase. Commands: 1 = read, 2 = write.
    // A read-back is a read repeating the track/sector of the write just
    // before it on the same drive; a data sector is a write outside the DOS
    // 3.3 catalog track 17.
    long calls = (long)tracer.calls.size(), reads = 0, writes = 0, others = 0;
    long perDrive[3] = {0, 0, 0}, readbacks = 0, dataSectors = 0, switches = 0;
    unsigned long long busy = 0, readCycles = 0, writeCycles = 0, backCycles = 0;
    for (long i = 0; i < calls; ++i) {
        const Call& c = tracer.calls[i];
        unsigned long long in = c.leave - c.enter;
        busy += in;
        if (c.drive >= 1 && c.drive <= 2) perDrive[c.drive]++;
        if (i > 0 && tracer.calls[i - 1].drive != c.drive) switches++;
        if (c.cmd == 1) {
            reads++;
            readCycles += in;
            const Call& p = tracer.calls[i > 0 ? i - 1 : 0];
            if (i > 0 && p.cmd == 2 && p.drive == c.drive && p.track == c.track &&
                p.sector == c.sector) {
                readbacks++;
                backCycles += in;
            }
        } else if (c.cmd == 2) {
            writes++;
            writeCycles += in;
            if (c.track != 17) dataSectors++;
        } else {
            others++;
        }
    }
    printf("copy A2FC, RWTS calls:       %ld = %ld read + %ld write + %ld other\n",
           calls, reads, writes, others);
    printf("copy A2FC, calls per drive:  %ld on drive 1, %ld on drive 2\n",
           perDrive[1], perDrive[2]);
    printf("copy A2FC, in RWTS:          %llu cycles; between calls: %llu cycles\n",
           busy, (unsigned long long)execute - busy);
    printf("copy A2FC, mean per read:    %llu cycles\n", reads ? readCycles / reads : 0);
    printf("copy A2FC, mean per write:   %llu cycles\n", writes ? writeCycles / writes : 0);
    printf("copy A2FC, mean per readback:%llu cycles over %ld read-backs\n",
           readbacks ? backCycles / readbacks : 0, readbacks);
    printf("copy A2FC, drive switches:   %ld\n", switches);
    printf("copy A2FC, data sectors:     %ld written, %.2f revolutions per sector\n",
           dataSectors, dataSectors ? execute / (double)dataSectors / 213000.0 : 0.0);

    assert(d->flushPendingWrites());
    puts("PASS: measured");
}

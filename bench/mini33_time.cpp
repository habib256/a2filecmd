// What a copy actually costs, on a real NMOS core with Disk II timing.
// Disposable images only (argv[2] boot, argv[3] target).
//
// Why measure cycles: at 1 MHz a Disk II revolution is about 200 000
// cycles. Every sector RWTS misses costs one whole revolution, and every
// change of drive costs a seek on top. So the interesting number is not
// how much work the code does but how many revolutions it waits through.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>

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
    expect(m, "3 FILES");

    // The catalog path on its own. The file count of the active panel
    // tells the two disks apart: 3 files on boot, 1 on the target. The
    // first switch pays the motor spin-up, the later ones do not.
    long to_target = timed(m, cpu, "/", "1 FILES");
    long warm[6];
    for (int i = 0; i < 3; ++i) {
        warm[i * 2] = timed(m, cpu, "/", "3 FILES");
        warm[i * 2 + 1] = timed(m, cpu, "/", "1 FILES");
    }
    m.pasteRawKeys("/", 1);
    run(cpu, 12000000);
    expect(m, "3 FILES");

    // Then the copy of A2FC.MINI, the largest file on the boot disk.
    m.pasteRawKeys("\t/\tK", 4);
    run(cpu, 24000000);
    expect(m, "A2FC.MINI");
    long prepare = timed(m, cpu, "C", "CANCEL");
    expect(m, "SOURCE S6 D1");
    long execute = timed(m, cpu, "Y", "COPY VERIFIED");

    printf("catalog, first switch to drive 2: %ld cycles\n", to_target);
    printf("catalog, warm switches:           %ld %ld %ld %ld %ld %ld cycles\n",
           warm[0], warm[1], warm[2], warm[3], warm[4], warm[5]);
    printf("copy A2FC.MINI, checking phase:   %ld cycles\n", prepare);
    printf("copy A2FC.MINI, writing phase:    %ld cycles\n", execute);
    printf("copy A2FC.MINI, total:            %ld cycles = %.1f s at 1 MHz\n",
           prepare + execute, (prepare + execute) / 1.0e6);
    assert(d->flushPendingWrites());
    puts("PASS: measured");
}

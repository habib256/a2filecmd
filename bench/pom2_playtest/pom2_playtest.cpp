// Minimal headless host for the POM2 core (GPL-3.0-or-later).
// No GUI or persistent settings. `--preset iie` (default): Apple //e
// Enhanced, HDV card slot 5, Mockingboard slot 2. `--preset iic`: Apple //c
// (32 KB ROM), whose slot 6 IS the built-in 5.25" drive and whose slot 5 is
// the machine's own SmartPort firmware -- the HDV rides it as a SmartPort
// unit on the rear port (POM2's IIcExternalSmartPort answers the bus), so a
// //c has no HDV *card* and no Mockingboard. Both presets boot a slot-6
// floppy with `--disk X --boot 6`; POM2's //c boots its internal drive from
// the ROM's own scan, and `bootFromSlot(6)` is that drive.
// `--ssc PORT`: a Super Serial Card in slot 2 with its TCP bridge listening
// on 127.0.0.1:PORT in RAW mode (no telnet negotiation: a $FF in a block
// passes as is), for A2 File Cmd's VDrive bench -- bench/vsdrive_server.py
// connects to it and serves a .po the way ADTPro's VDrive does. On the //e
// preset the SSC takes the Mockingboard's slot 2 (a serial bench needs no
// sound); on the //c, slot 2 is the modem port, where a real //c has it.
// `--uthernet`: an Uthernet II (WIZnet W5100, hardware TCP/IP) in slot 3
// of the //e preset, with the loopback fence lowered so the guest can reach
// a server on 127.0.0.1 — the network twin of `--ssc` for the same VDrive
// bench, where the Apple II side connects to `vsdrive_server.py` over a
// W5100 TCP socket instead of the serial line. The W5100's TCP/UDP sockets
// are host sockets, so no Ethernet backend is needed. The //c has no slot.
// `--preset iie_unenh` (alias `iie-u`): the 1983 //e — 16 KB firmware
// 342-0135/0134 (no MouseText, $FBC0 = $EA, MACHID reads it as a plain //e),
// the 2 KB character ROM, and a NMOS 6502: a 65C02 opcode (stz, bra, phx…)
// executes as the NMOS undocumented one or traps, instead of working. It is
// the machine A2 File Cmd's `ARCH=6502` build (`A2FILECMD-6502.po`) is for,
// and the only one that can prove it. Same slot map as `iie`.
// `--preset iie_nmos`: the enhanced //e firmware and character ROM with a
// NMOS 6502 put back in its socket -- the machine where a firmware check
// alone lets 65C02 code run on the wrong processor. Same slot map as `iie`.
// `--chatmauve [feline|iic|eve|video7|rvb|rvbgraph]`: the Le Chat Mauve RGB card
// in slot 7 (the GUI's fresh-install slot; variant Féline by default, the
// //c adapter on the //c preset) with the display on its RGB pipeline, so
// `/screen.ppm` shows what the GUI shows with the card — A2 File Cmd's image
// viewer misbehaves only with the card plugged, and the headless bench could
// not see it. The variant is consumed only when the next word is one of the
// five keys, so `--chatmauve disk.hdv` still takes the disk.
// `--printer-ssc LOG`: a Super Serial Card in slot 1 with its printer tap on
// and no host transport -- the printer a //e keeps in slot 1, or the //c's
// port 1 (the printer port). Every access to its device-select registers
// ($C0n0-$C0nF: $C098-$C09F in slot 1) is appended to LOG as it happens,
// one line each: `W r v` for a write of v to register r (0-F; 8-B are the
// 6551, 1 and 2 the DIP switches), `R r v` for a read; slot-ROM reads
// are not logged (a signature check is harmless). A2 File Cmd's printer
// bench (bench/vdrive_printer.py) asserts the file stays empty of writes.
// On the //c preset, without `--ssc`, port 2 (slot 2) gets a plain,
// transport-less SSC too: a real //c always has both ports.
// `--printer-slot N` (2-7, //e presets): the --printer-ssc card goes in
// slot N instead of slot 1, its mode switches (DIP bank 1 at $C0n1, bits
// $03) set to printer; `--ssc-slot N` (2-7, //e presets) moves the --ssc
// card, set to communications mode, the same way. Together they put a
// printer SSC in slot 2 and VDrive's host in slot 4 (bench/vdrive_printer.py).
// Both need a POM2 library with the SSC's DIP switches (SuperSerialCard::
// setMode, shipped with PrinterPortControl.h); built against an older one,
// they are unknown flags (exit code 2).
// Exit codes: 2 = unknown flag (probed by the benches, before anything
// else), 3 = no disk / bad port / a card the preset cannot take.
#include "EmulationController.h"
#include "AiControlServer.h"
#include "Apple2Display.h"
#include "ProDOSHardDiskCard.h"
#include "Mockingboard.h"
#include "MouseCardAppleWin.h"
#include "DiskIICard.h"
#include "LeChatMauveCard.h"
#include "SmartPortCard.h"
#include "SmartPortHdvUnit.h"
#include "SmartPort35Unit.h"
#include "SuperSerialCard.h"
#include "SuperSerialTcpTransport.h"
#include "SuperSerialTransport.h"
#include "UthernetIICard.h"
#include "W5100Device.h"
#if __has_include("PrinterPortControl.h")
#define HAVE_SSC_DIP 1          // SuperSerialCard::setMode, the DIP switches
#endif
#include <string>
#include <csignal>
#include <cstdio>
#include <stdexcept>
#include <iostream>

static volatile std::sig_atomic_t stopped = 0;

// The printer SSC of --printer-ssc (slot 1, or --printer-slot): the card itself, plus a line per
// device-select access, flushed at once (a bench may SIGKILL the host).
class LoggingSsc : public SuperSerialCard {
public:
    LoggingSsc(int slot, const std::string& path) : SuperSerialCard(slot), log_(std::fopen(path.c_str(), "w")) {
        if (!log_) throw std::runtime_error("cannot write " + path);
    }
    ~LoggingSsc() override { if (log_) std::fclose(log_); }
    uint8_t deviceSelectRead(uint8_t low4) override {
        const uint8_t v = SuperSerialCard::deviceSelectRead(low4);
        std::fprintf(log_, "R %X %02X\n", low4 & 15, v);
        std::fflush(log_);
        return v;
    }
    void deviceSelectWrite(uint8_t low4, uint8_t v) override {
        std::fprintf(log_, "W %X %02X\n", low4 & 15, v);
        std::fflush(log_);
        SuperSerialCard::deviceSelectWrite(low4, v);
    }
private:
    std::FILE* log_;
};
static void stop(int) { stopped = 1; }

int main(int argc, char** argv) {
    try {
        int port = 6503, speed = 200000, bootSlot = 5, sscPort = 0;
        int printerSlot = 1, sscSlot = 2;
        bool mouse = false, uthernet = false, chatMauve = false;
        LeChatMauveCard::Variant lcmVariant = LeChatMauveCard::Variant::Feline;
        bool lcmVariantGiven = false;
        std::string disk, disk2, floppy, floppy2, preset = "iie", printerLog;
        for (int i = 1; i < argc; ++i) {
            std::string a = argv[i];
            if (a == "--preset" && i + 1 < argc) {
                preset = argv[++i];
                if (preset == "iie-u") preset = "iie_unenh";
                if (preset != "iie" && preset != "iic" && preset != "iie_unenh" && preset != "iie_nmos") return 2;
            } else if (a == "--speed" && i + 1 < argc) speed = std::stoi(argv[++i]);
            // --disk : une disquette 5,25 pouces dans un Disk II en slot 6.
            else if (a == "--disk" && i + 1 < argc) floppy = argv[++i];
            // --disk2 : une seconde disquette dans le lecteur 2 du meme Disk II,
            // presente des l'amorcage (le banc des disques physiques d'A2 File
            // Cmd : un vrai DOS 3.3 dans un lecteur, sans passer par /disk).
            else if (a == "--disk2" && i + 1 < argc) floppy2 = argv[++i];
            // --hd2 : un second disque dur, lecteur 2 de la carte HDV du slot 5
            // (S5,D2) : le volume de plus de 4 096 blocs que FIXIT et REPAIR
            // examinent sans qu'il soit celui du programme.
            else if (a == "--hd2" && i + 1 < argc) disk2 = argv[++i];
            // --boot 6 : amorcer la disquette plutot que le disque dur.
            else if (a == "--boot" && i + 1 < argc) bootSlot = std::stoi(argv[++i]);
            // --mouse : une AppleMouse II (HLE AppleWin) en slot 4 ;
            // POST /mouse la fait bouger.
            else if (a == "--mouse") mouse = true;
            // --ssc PORT : la Super Serial Card en slot 2, pont TCP en mode
            // brut, pour le banc VDrive d'A2 File Cmd (bench/vdrive.py).
            else if (a == "--ssc" && i + 1 < argc) sscPort = std::stoi(argv[++i]);
            // --printer-ssc LOG : une SSC imprimante en slot 1, chaque acces
            // a ses registres journalise dans LOG (bench/vdrive_printer.py).
            else if (a == "--printer-ssc" && i + 1 < argc) printerLog = argv[++i];
#ifdef HAVE_SSC_DIP
            // --printer-slot N / --ssc-slot N : ces deux cartes ailleurs
            // (commutateurs en mode imprimante / communication).
            else if (a == "--printer-slot" && i + 1 < argc) printerSlot = std::stoi(argv[++i]);
            else if (a == "--ssc-slot" && i + 1 < argc) sscSlot = std::stoi(argv[++i]);
#endif
            // --uthernet : une Uthernet II (W5100) en slot 3, loopback ouvert,
            // pour la version reseau du banc VDrive d'A2 File Cmd.
            else if (a == "--uthernet") uthernet = true;
            // --chatmauve [variante] : Le Chat Mauve RGB en slot 7, l'ecran
            // sur son pipeline RGB (le banc de la visionneuse d'A2 File Cmd).
            else if (a == "--chatmauve") {
                chatMauve = true;
                // The settings token for the RVB Graph is `rvb`; the bench
                // spells it out, so take both.
                if (i + 1 < argc && (LeChatMauveCard::parseVariant(argv[i + 1], lcmVariant)
                                     || std::string(argv[i + 1]) == "rvbgraph")) {
                    if (std::string(argv[i + 1]) == "rvbgraph")
                        lcmVariant = LeChatMauveCard::Variant::RvbGraph;
                    lcmVariantGiven = true;
                    ++i;
                }
            }
            else if (a.rfind("--ai-control=", 0) == 0) port = std::stoi(a.substr(13));
            else if (!a.empty() && a[0] != '-' && disk.empty()) disk = a;
            else return 2;
        }
        if (disk.empty() || port < 1 || port > 65535 || speed < 1) return 3;
        if (sscPort < 0 || sscPort > 65535 || sscPort == port) return 3;
        if (printerSlot < 1 || printerSlot > 7 || sscSlot < 2 || sscSlot > 7) return 3;
        if (uthernet && preset == "iic") return 3;   // no physical slot on a //c
        if (!disk2.empty() && preset == "iic") return 3;   // the //c bench has one HDV unit
        const bool iic = (preset == "iic");
        const bool unenh = (preset == "iie_unenh");
        const bool nmos = unenh || preset == "iie_nmos";
        // The //c's ports are where they are; slot 5 and 6 hold the disks.
        if (iic && (printerSlot != 1 || sscSlot != 2)) return 3;
        if (printerSlot == 5 || printerSlot == 6 || sscSlot == 5 || sscSlot == 6) return 3;
        if (!printerLog.empty() && sscPort && printerSlot == sscSlot) return 3;
        EmulationController ctrl;
        auto& mem = ctrl.memory();
        mem.setIIEMode(true);
        if (iic) {
            // A //c 32 KB dump is two firmware banks; the loader takes the
            // lower one (what POM2's own profile switch does for the //c).
            if (!mem.loadAppleIIRom(POM2_ROOT "/roms/apple2c-32Kv0.rom", /*pickLowerHalf=*/true) &&
                !mem.loadAppleIIRom(POM2_ROOT "/roms/apple2c-16K.rom", /*pickLowerHalf=*/true))
                throw std::runtime_error("Apple //c ROM unavailable");
        } else if (unenh) {
            // The original 1983 firmware (342-0135-B + 342-0134-A, 16 KB) —
            // POM2's "Apple //e Unenhanced" profile probes the same dumps.
            if (!mem.loadAppleIIRom(POM2_ROOT "/roms/apple2e_unenh.rom") &&
                !mem.loadAppleIIRom(POM2_ROOT "/roms/342-0135-b.64.rom"))
                throw std::runtime_error("Apple //e Unenhanced ROM unavailable");
        } else if (!mem.loadAppleIIRom(POM2_ROOT "/roms/apple2e.rom")) {
            throw std::runtime_error("Apple IIe ROM unavailable");
        }
        // The 1983 //e shipped the 2 KB character generator: no MouseText,
        // so ALTCHAR shows inverse lowercase at $40-$5F, as on the machine.
        if (!mem.loadCharRom(unenh ? POM2_ROOT "/roms/apple2e_char_2k.rom"
                                   : POM2_ROOT "/roms/apple2e_char_us.rom"))
            throw std::runtime_error("Character ROM unavailable");
        // A 65C02 is soldered on the Enhanced //e and the //c; the 1983 //e
        // has a NMOS 6502, and a build meant for it must run on one.
        ctrl.cpu().setCpuMode(nmos ? M6502::CpuMode::NMOS : M6502::CpuMode::CMOS);
        ProDOSHardDiskCard* diskCard = nullptr;
        pom2::SmartPortHdvUnit* spUnit = nullptr;
        if (iic) {
            // Slot 5 of a //c is the machine's SmartPort firmware; the disk
            // hangs off the rear port as unit 0 of the slot-5 card, served
            // over the bus by the controller's IIcExternalSmartPort.
            auto sp = std::make_unique<pom2::SmartPortCard>(5);
            auto unit = std::make_unique<pom2::SmartPortHdvUnit>();
            if (!unit->loadImage(disk)) throw std::runtime_error("Cannot load HDV");
            unit->setWriteBackEnabled(true);   // meme politique que la carte HDV, ci-dessous
            spUnit = unit.get();
            sp->setUnit(0, std::move(unit));
            sp->setUnit(1, std::make_unique<pom2::SmartPort35Unit>());
            mem.slotBus().plug(5, std::move(sp));
        } else {
            auto hdv = std::make_unique<ProDOSHardDiskCard>(5);
            if (!hdv->loadImage(disk)) throw std::runtime_error("Cannot load HDV");
            // Ecriture differee activee, comme pour le Disk II : les bancs
            // relisent l'image apres l'arret pour comparer ses octets, et
            // POM2 ne recopie les blocs modifies que si on le lui demande
            // (flushBay a l'arret, ci-dessous).
            hdv->setWriteBackEnabled(true);
            if (!disk2.empty()) {
                if (!hdv->loadDrive(1, disk2)) throw std::runtime_error("Cannot load HDV 2");
                hdv->setBayWriteBack(1, true);
            }
            diskCard = hdv.get();
            mem.slotBus().plug(5, std::move(hdv));
            if (!sscPort && !(!printerLog.empty() && printerSlot == 2))
                mem.slotBus().plug(2, std::make_unique<MockingboardCard>(2));
        }
        SuperSerialCard* ssc = nullptr;
        if (sscPort) {
            // The driver (a2filecmd src/vsdrive.s) scans $C1..$C7 for the
            // Pascal signature, probes the 6551's command register, then
            // writes control $10 (16x external clock = 115 200 in its book;
            // POM2 paces that index as unconstrained) and command $0B.
            auto card = std::make_unique<SuperSerialCard>(sscSlot);
#ifdef HAVE_SSC_DIP
            card->setMode(SuperSerialCard::Mode::Communications);
#endif
            card->setRawMode(true);
            // A VDrive cable (USB-serial, null-modem) has no carrier: the
            // host going away is silence and a timeout, not a DCD drop —
            // which, on a driver with no interrupt handler, is ProDOS's
            // "RESTART SYSTEM - $01". Tie the modem lines.
            card->setModemLinesTied(true);
            card->setTransport(pom2::makeSuperSerialTcpTransport(*card, sscSlot));
            ssc = card.get();
            mem.slotBus().plug(sscSlot, std::move(card));
        }
        if (!printerLog.empty()) {
            auto card = std::make_unique<LoggingSsc>(printerSlot, printerLog);
#ifdef HAVE_SSC_DIP
            card->setMode(SuperSerialCard::Mode::Printer);
#endif
            card->setPrinterTap(true);
            mem.slotBus().plug(printerSlot, std::move(card));
            if (iic && !sscPort) mem.slotBus().plug(2, std::make_unique<SuperSerialCard>(2));
        }
        if (uthernet) {
            // No ROM on this card: a driver finds it by probing the W5100's
            // mode register through the $C0n4-$C0n7 window (AppleWin/IP65
            // convention). Loopback is a security fence in the GUI (the
            // guest's sockets are host sockets); this is a test rig whose
            // server lives on 127.0.0.1, so it comes down here.
            auto card = std::make_unique<pom2::UthernetIICard>(3);
            card->chip().setAllowLoopback(true);
            mem.slotBus().plug(3, std::move(card));
        }
        if (mouse) {
            auto card = std::make_unique<MouseCardAppleWin>(4);
            if (!card->loadRom(POM2_ROOT "/roms/mouse_341-0270-c.bin")) throw std::runtime_error("mouse ROM unavailable");
            mem.slotBus().plug(4, std::move(card));
        }
        DiskIICard* floppyCard = nullptr;
        // A //c always has its drive: the rear SmartPort port is decoded off
        // the Disk II's own soft switches ($C0E0-$C0EF), so without the card
        // in slot 6 the firmware's bus probe at $CC2C never gets an answer
        // and the HDV on slot 5 is never found. Plug it empty if need be.
        if (!floppy.empty() || !floppy2.empty() || iic) {
            auto card = std::make_unique<DiskIICard>();
            if (!card->loadBootRom(POM2_ROOT "/roms/disk2.rom")) throw std::runtime_error("disk2.rom unavailable");
            (void)card->loadLssRom(POM2_ROOT "/roms/diskii_p6.rom");
            // Ecriture autorisee, sinon le lecteur se presente protege en
            // ecriture (politique par defaut de POM2) ; le banc travaille sur
            // une copie, recopiee dans le fichier a l'arret.
            card->setWriteBackEnabled(true);
            if (!floppy.empty()) {
                if (!card->insertDisk(floppy)) throw std::runtime_error("Cannot insert floppy: " + card->getLastError());
                card->seekTrack0();
            }
            if (!floppy2.empty() && !card->insertDisk(1, floppy2))
                throw std::runtime_error("Cannot insert floppy 2: " + card->getLastError(1));
            // The //c's built-in drive shares the machine's IWM.
            if (iic) card->setIWM(&ctrl.iwm());
            floppyCard = card.get();
            mem.slotBus().plug(6, std::move(card));
        }
        LeChatMauveCard* lcm = nullptr;
        if (chatMauve) {
            // What MainWindow_SlotConfig.cpp's plugChatMauve does: the //c
            // takes only its rear-port adapter, every other machine the
            // variant asked for (Féline by default); the card programs
            // Memory's aux shadow itself (the Eve's CPREG auto-write).
            if (iic && !lcmVariantGiven) lcmVariant = LeChatMauveCard::Variant::IIcAdapter;
            auto card = std::make_unique<LeChatMauveCard>(7, lcmVariant);
            lcm = card.get();
            lcm->setMemory(&mem);
            mem.slotBus().plug(7, std::move(card));
        }
        if (bootSlot == 6 && !floppyCard) return 2;
        if (!ctrl.bootFromSlot(bootSlot)) throw std::runtime_error("Cannot boot slot " + std::to_string(bootSlot));
        ctrl.setCyclesPerFrame(speed);
        Apple2Display display;
        // Match the GUI host: 80-column text and DHGR need the AUX plane.
        display.setAuxMemory(mem.auxData());
        if (lcm) {
            // The GUI re-points the display at the card on every rebuild and
            // the user picks the "RGB card - Le Chat Mauve" pipeline; both
            // here, so /screen.ppm is the card's picture, not the NTSC one.
            display.setChatMauveCard(lcm);
            display.setHiResMode(Apple2Display::HiResMode::ChatMauveRGB);
        }
        pom2::AiControlServer server;
        server.attach(&ctrl, &display, floppyCard, diskCard);   // floppyCard : POST /disk et /eject pilotent le Disk II (banc des images disque d'A2 File Cmd)
        server.setProfileLabel(iic   ? "Apple //c (headless)"
                             : unenh ? "Apple //e Unenhanced (headless)"
                             : nmos  ? "Apple //e Enhanced, NMOS 6502 (headless)"
                                     : "Apple //e Enhanced (headless)");
        if (!server.start(static_cast<uint16_t>(port))) return 1;
        if (ssc && !ssc->startListening(static_cast<uint16_t>(sscPort)))
            throw std::runtime_error("SSC: cannot listen on 127.0.0.1:" + std::to_string(sscPort));
        std::signal(SIGTERM, stop);
        std::signal(SIGINT, stop);
        ctrl.start();
        ctrl.setMode(EmulationController::Mode::Running);
        while (!stopped) std::this_thread::sleep_for(std::chrono::milliseconds(100));
        server.stop();
        ctrl.stop();
        if (floppyCard) (void)floppyCard->flushPendingWrites();
        if (diskCard) {
            std::string err;
            if (!diskCard->flushBay(0, err)) std::cerr << "HDV write-back failed: " << err << '\n';
            if (!disk2.empty() && !diskCard->flushBay(1, err))
                std::cerr << "HDV 2 write-back failed: " << err << '\n';
        }
        if (spUnit && !spUnit->saveDirty()) std::cerr << "SmartPort HDV write-back failed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}

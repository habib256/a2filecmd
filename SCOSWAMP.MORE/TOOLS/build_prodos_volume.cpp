#include "ProDOSVolume.h"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

static bool readFile(const std::string& path, std::vector<std::uint8_t>& out)
{
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    out.assign(std::istreambuf_iterator<char>(in), {});
    return in.good() || in.eof();
}

int main(int argc, char** argv)
{
    if (argc != 4) {
        std::cerr << "usage: build_prodos_volume FOLDER BOOT_TEMPLATE OUTPUT.HDV\n";
        return 2;
    }
    std::vector<std::uint8_t> volume;
    const auto built = pom2::buildVolumeFromFolder(argv[1], "SCOSWAMP", volume);
    if (!built.ok) {
        std::cerr << "build failed: " << built.error << '\n';
        return 1;
    }
    std::vector<std::uint8_t> boot;
    if (!readFile(argv[2], boot) || boot.size() < 1024 || volume.size() < 1024) {
        std::cerr << "boot template must contain at least two 512-byte blocks\n";
        return 1;
    }
    std::copy_n(boot.begin(), 1024, volume.begin());

    // ProDOS 8 expects the compatibility fields duplicated in bytes $15-$1B
    // of every subdirectory header.  POM2's folder builder deliberately
    // leaves them blank, which its host decoder tolerates, but BASIC.SYSTEM
    // then reports FILE NOT FOUND for otherwise valid directory entries.
    // Match the layout written by the original working SCOSWAMP volume.
    for (std::size_t block = 2; block * 512 + 43 <= volume.size(); ++block) {
        auto* header = volume.data() + block * 512 + 4;
        if ((header[0] >> 4) != 0x0e || header[0x10] != 0x75) continue;
        header[0x11] = 0x24;
        header[0x12] = 0x00;
        header[0x13] = 0xc3;
        header[0x14] = 0x27;
        header[0x15] = 0x0d;
        header[0x16] = 0x00;
        header[0x17] = 0x00;
    }

    // The host filename SCOSWAMP.BIN maps to ProDOS name SCOSWAMP and type
    // BIN, but a plain extension carries no cc65 load address. Patch its
    // root-directory aux type so BASIC.SYSTEM's BRUN loads it at $4000.
    bool patchedLoadAddress = false;
    for (std::size_t block = 2; block <= 5 && !patchedLoadAddress; ++block) {
        for (std::size_t off = 4; off + 39 <= 512; off += 39) {
            auto* entry = volume.data() + block * 512 + off;
            const std::size_t nameLen = entry[0] & 0x0f;
            if (nameLen == 8 && std::equal(entry + 1, entry + 9, "SCOSWAMP") &&
                entry[0x10] == 0x06) {
                entry[0x1f] = 0x00;
                entry[0x20] = 0x40;
                patchedLoadAddress = true;
                break;
            }
        }
    }
    if (!patchedLoadAddress) {
        std::cerr << "SCOSWAMP BIN entry not found\n";
        return 1;
    }
    std::ofstream out(argv[3], std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char*>(volume.data()),
              static_cast<std::streamsize>(volume.size()));
    if (!out) {
        std::cerr << "cannot write " << argv[3] << '\n';
        return 1;
    }
    std::cout << "SCOSWAMP: " << built.filesIncluded << " files, "
              << built.totalBlocks << " blocks\n";
}

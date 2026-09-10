/*****************************************************************************/
/*                                                                           */
/*                                opcw65c02.c                                */
/*                                                                           */
/*                      W65C02 opcode description table                      */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/* (C) 2003-2011, Ullrich von Bassewitz                                      */
/*                Roemerstrasse 52                                           */
/*                D-70794 Filderstadt                                        */
/* EMail:         uz@cc65.org                                                */
/*                                                                           */
/*                                                                           */
/* This software is provided 'as-is', without any expressed or implied       */
/* warranty.  In no event will the authors be held liable for any damages    */
/* arising from the use of this software.                                    */
/*                                                                           */
/* Permission is granted to anyone to use this software for any purpose,     */
/* including commercial applications, and to alter it and redistribute it    */
/* freely, subject to the following restrictions:                            */
/*                                                                           */
/* 1. The origin of this software must not be misrepresented; you must not   */
/*    claim that you wrote the original software. If you use this software   */
/*    in a product, an acknowledgment in the product documentation would be  */
/*    appreciated but is not required.                                       */
/* 2. Altered source versions must be plainly marked as such, and must not   */
/*    be misrepresented as being the original software.                      */
/* 3. This notice may not be removed or altered from any source              */
/*    distribution.                                                          */
/*                                                                           */
/*****************************************************************************/




/* Altered for A2FC: compact mnemonic/mode table, derived from cc65 da65
 * opc6502.c and opcw65c02.c. 65C02 includes Rockwell bit operations and
 * WDC WAI/STP. Reserved/undocumented opcodes remain individual data bytes.
 * Upstream: https://github.com/cc65/cc65/tree/master/src/da65 */
enum { AM_ILLEGAL, AM_IMPLICIT, AM_ACCUMULATOR, AM_IMMEDIATE, AM_DIRECT, AM_DIRECTX, AM_DIRECTY, AM_ABSOLUTE, AM_ABSOLUTEX, AM_ABSOLUTEY, AM_DIRECTXINDIRECT, AM_DIRECTINDIRECTY, AM_DIRECTINDIRECT, AM_JMPABSOLUTEINDIRECT, AM_ABSOLUTEXINDIRECT, AM_RELATIVE, AM_BITBRANCH };
static const unsigned char lengths[] = {1,1,1,2,2,2,2,3,3,3,2,2,2,3,3,2,3};
static const char mnemonics[][6] = {
    ".BYTE", "ADC", "AND", "ASL", "BBR0", "BBR1", "BBR2", "BBR3", "BBR4", "BBR5", "BBR6", "BBR7", "BBS0", "BBS1", "BBS2", "BBS3", "BBS4", "BBS5", "BBS6", "BBS7", "BCC", "BCS", "BEQ", "BIT", "BMI", "BNE", "BPL", "BRA", "BRK", "BVC", "BVS", "CLC", "CLD", "CLI", "CLV", "CMP", "CPX", "CPY", "DEC", "DEX", "DEY", "EOR", "INC", "INX", "INY", "JMP", "JSR", "LDA", "LDX", "LDY", "LSR", "NOP", "ORA", "PHA", "PHP", "PHX", "PHY", "PLA", "PLP", "PLX", "PLY", "RMB0", "RMB1", "RMB2", "RMB3", "RMB4", "RMB5", "RMB6", "RMB7", "ROL", "ROR", "RTI", "RTS", "SBC", "SEC", "SED", "SEI", "SMB0", "SMB1", "SMB2", "SMB3", "SMB4", "SMB5", "SMB6", "SMB7", "STA", "STP", "STX", "STY", "STZ", "TAX", "TAY", "TRB", "TSB", "TSX", "TXA", "TXS", "TYA", "WAI"
};
/* The high bit of mode marks a CMOS-only opcode. */
struct Opcode { unsigned char name, mode; };
static const struct Opcode opcodes[256] = {
    {28, AM_IMPLICIT}, /* 00 BRK */
    {52, AM_DIRECTXINDIRECT}, /* 01 ORA */
    {0, AM_ILLEGAL}, /* 02  */
    {0, AM_ILLEGAL}, /* 03  */
    {93, AM_DIRECT | 0x80}, /* 04 TSB */
    {52, AM_DIRECT}, /* 05 ORA */
    {3, AM_DIRECT}, /* 06 ASL */
    {61, AM_DIRECT | 0x80}, /* 07 RMB0 */
    {54, AM_IMPLICIT}, /* 08 PHP */
    {52, AM_IMMEDIATE}, /* 09 ORA */
    {3, AM_ACCUMULATOR}, /* 0A ASL */
    {0, AM_ILLEGAL}, /* 0B  */
    {93, AM_ABSOLUTE | 0x80}, /* 0C TSB */
    {52, AM_ABSOLUTE}, /* 0D ORA */
    {3, AM_ABSOLUTE}, /* 0E ASL */
    {4, AM_BITBRANCH | 0x80}, /* 0F BBR0 */
    {26, AM_RELATIVE}, /* 10 BPL */
    {52, AM_DIRECTINDIRECTY}, /* 11 ORA */
    {52, AM_DIRECTINDIRECT | 0x80}, /* 12 ORA */
    {0, AM_ILLEGAL}, /* 13  */
    {92, AM_DIRECT | 0x80}, /* 14 TRB */
    {52, AM_DIRECTX}, /* 15 ORA */
    {3, AM_DIRECTX}, /* 16 ASL */
    {62, AM_DIRECT | 0x80}, /* 17 RMB1 */
    {31, AM_IMPLICIT}, /* 18 CLC */
    {52, AM_ABSOLUTEY}, /* 19 ORA */
    {42, AM_ACCUMULATOR | 0x80}, /* 1A INC */
    {0, AM_ILLEGAL}, /* 1B  */
    {92, AM_ABSOLUTE | 0x80}, /* 1C TRB */
    {52, AM_ABSOLUTEX}, /* 1D ORA */
    {3, AM_ABSOLUTEX}, /* 1E ASL */
    {5, AM_BITBRANCH | 0x80}, /* 1F BBR1 */
    {46, AM_ABSOLUTE}, /* 20 JSR */
    {2, AM_DIRECTXINDIRECT}, /* 21 AND */
    {0, AM_ILLEGAL}, /* 22  */
    {0, AM_ILLEGAL}, /* 23  */
    {23, AM_DIRECT}, /* 24 BIT */
    {2, AM_DIRECT}, /* 25 AND */
    {69, AM_DIRECT}, /* 26 ROL */
    {63, AM_DIRECT | 0x80}, /* 27 RMB2 */
    {58, AM_IMPLICIT}, /* 28 PLP */
    {2, AM_IMMEDIATE}, /* 29 AND */
    {69, AM_ACCUMULATOR}, /* 2A ROL */
    {0, AM_ILLEGAL}, /* 2B  */
    {23, AM_ABSOLUTE}, /* 2C BIT */
    {2, AM_ABSOLUTE}, /* 2D AND */
    {69, AM_ABSOLUTE}, /* 2E ROL */
    {6, AM_BITBRANCH | 0x80}, /* 2F BBR2 */
    {24, AM_RELATIVE}, /* 30 BMI */
    {2, AM_DIRECTINDIRECTY}, /* 31 AND */
    {2, AM_DIRECTINDIRECT | 0x80}, /* 32 AND */
    {0, AM_ILLEGAL}, /* 33  */
    {23, AM_DIRECTX | 0x80}, /* 34 BIT */
    {2, AM_DIRECTX}, /* 35 AND */
    {69, AM_DIRECTX}, /* 36 ROL */
    {64, AM_DIRECT | 0x80}, /* 37 RMB3 */
    {74, AM_IMPLICIT}, /* 38 SEC */
    {2, AM_ABSOLUTEY}, /* 39 AND */
    {38, AM_ACCUMULATOR | 0x80}, /* 3A DEC */
    {0, AM_ILLEGAL}, /* 3B  */
    {23, AM_ABSOLUTEX | 0x80}, /* 3C BIT */
    {2, AM_ABSOLUTEX}, /* 3D AND */
    {69, AM_ABSOLUTEX}, /* 3E ROL */
    {7, AM_BITBRANCH | 0x80}, /* 3F BBR3 */
    {71, AM_IMPLICIT}, /* 40 RTI */
    {41, AM_DIRECTXINDIRECT}, /* 41 EOR */
    {0, AM_ILLEGAL}, /* 42  */
    {0, AM_ILLEGAL}, /* 43  */
    {0, AM_ILLEGAL}, /* 44  */
    {41, AM_DIRECT}, /* 45 EOR */
    {50, AM_DIRECT}, /* 46 LSR */
    {65, AM_DIRECT | 0x80}, /* 47 RMB4 */
    {53, AM_IMPLICIT}, /* 48 PHA */
    {41, AM_IMMEDIATE}, /* 49 EOR */
    {50, AM_ACCUMULATOR}, /* 4A LSR */
    {0, AM_ILLEGAL}, /* 4B  */
    {45, AM_ABSOLUTE}, /* 4C JMP */
    {41, AM_ABSOLUTE}, /* 4D EOR */
    {50, AM_ABSOLUTE}, /* 4E LSR */
    {8, AM_BITBRANCH | 0x80}, /* 4F BBR4 */
    {29, AM_RELATIVE}, /* 50 BVC */
    {41, AM_DIRECTINDIRECTY}, /* 51 EOR */
    {41, AM_DIRECTINDIRECT | 0x80}, /* 52 EOR */
    {0, AM_ILLEGAL}, /* 53  */
    {0, AM_ILLEGAL}, /* 54  */
    {41, AM_DIRECTX}, /* 55 EOR */
    {50, AM_DIRECTX}, /* 56 LSR */
    {66, AM_DIRECT | 0x80}, /* 57 RMB5 */
    {33, AM_IMPLICIT}, /* 58 CLI */
    {41, AM_ABSOLUTEY}, /* 59 EOR */
    {56, AM_IMPLICIT | 0x80}, /* 5A PHY */
    {0, AM_ILLEGAL}, /* 5B  */
    {0, AM_ILLEGAL}, /* 5C  */
    {41, AM_ABSOLUTEX}, /* 5D EOR */
    {50, AM_ABSOLUTEX}, /* 5E LSR */
    {9, AM_BITBRANCH | 0x80}, /* 5F BBR5 */
    {72, AM_IMPLICIT}, /* 60 RTS */
    {1, AM_DIRECTXINDIRECT}, /* 61 ADC */
    {0, AM_ILLEGAL}, /* 62  */
    {0, AM_ILLEGAL}, /* 63  */
    {89, AM_DIRECT | 0x80}, /* 64 STZ */
    {1, AM_DIRECT}, /* 65 ADC */
    {70, AM_DIRECT}, /* 66 ROR */
    {67, AM_DIRECT | 0x80}, /* 67 RMB6 */
    {57, AM_IMPLICIT}, /* 68 PLA */
    {1, AM_IMMEDIATE}, /* 69 ADC */
    {70, AM_ACCUMULATOR}, /* 6A ROR */
    {0, AM_ILLEGAL}, /* 6B  */
    {45, AM_JMPABSOLUTEINDIRECT}, /* 6C JMP */
    {1, AM_ABSOLUTE}, /* 6D ADC */
    {70, AM_ABSOLUTE}, /* 6E ROR */
    {10, AM_BITBRANCH | 0x80}, /* 6F BBR6 */
    {30, AM_RELATIVE}, /* 70 BVS */
    {1, AM_DIRECTINDIRECTY}, /* 71 ADC */
    {1, AM_DIRECTINDIRECT | 0x80}, /* 72 ADC */
    {0, AM_ILLEGAL}, /* 73  */
    {89, AM_DIRECTX | 0x80}, /* 74 STZ */
    {1, AM_DIRECTX}, /* 75 ADC */
    {70, AM_DIRECTX}, /* 76 ROR */
    {68, AM_DIRECT | 0x80}, /* 77 RMB7 */
    {76, AM_IMPLICIT}, /* 78 SEI */
    {1, AM_ABSOLUTEY}, /* 79 ADC */
    {60, AM_IMPLICIT | 0x80}, /* 7A PLY */
    {0, AM_ILLEGAL}, /* 7B  */
    {45, AM_ABSOLUTEXINDIRECT | 0x80}, /* 7C JMP */
    {1, AM_ABSOLUTEX}, /* 7D ADC */
    {70, AM_ABSOLUTEX}, /* 7E ROR */
    {11, AM_BITBRANCH | 0x80}, /* 7F BBR7 */
    {27, AM_RELATIVE | 0x80}, /* 80 BRA */
    {85, AM_DIRECTXINDIRECT}, /* 81 STA */
    {0, AM_ILLEGAL}, /* 82  */
    {0, AM_ILLEGAL}, /* 83  */
    {88, AM_DIRECT}, /* 84 STY */
    {85, AM_DIRECT}, /* 85 STA */
    {87, AM_DIRECT}, /* 86 STX */
    {77, AM_DIRECT | 0x80}, /* 87 SMB0 */
    {40, AM_IMPLICIT}, /* 88 DEY */
    {23, AM_IMMEDIATE | 0x80}, /* 89 BIT */
    {95, AM_IMPLICIT}, /* 8A TXA */
    {0, AM_ILLEGAL}, /* 8B  */
    {88, AM_ABSOLUTE}, /* 8C STY */
    {85, AM_ABSOLUTE}, /* 8D STA */
    {87, AM_ABSOLUTE}, /* 8E STX */
    {12, AM_BITBRANCH | 0x80}, /* 8F BBS0 */
    {20, AM_RELATIVE}, /* 90 BCC */
    {85, AM_DIRECTINDIRECTY}, /* 91 STA */
    {85, AM_DIRECTINDIRECT | 0x80}, /* 92 STA */
    {0, AM_ILLEGAL}, /* 93  */
    {88, AM_DIRECTX}, /* 94 STY */
    {85, AM_DIRECTX}, /* 95 STA */
    {87, AM_DIRECTY}, /* 96 STX */
    {78, AM_DIRECT | 0x80}, /* 97 SMB1 */
    {97, AM_IMPLICIT}, /* 98 TYA */
    {85, AM_ABSOLUTEY}, /* 99 STA */
    {96, AM_IMPLICIT}, /* 9A TXS */
    {0, AM_ILLEGAL}, /* 9B  */
    {89, AM_ABSOLUTE | 0x80}, /* 9C STZ */
    {85, AM_ABSOLUTEX}, /* 9D STA */
    {89, AM_ABSOLUTEX | 0x80}, /* 9E STZ */
    {13, AM_BITBRANCH | 0x80}, /* 9F BBS1 */
    {49, AM_IMMEDIATE}, /* A0 LDY */
    {47, AM_DIRECTXINDIRECT}, /* A1 LDA */
    {48, AM_IMMEDIATE}, /* A2 LDX */
    {0, AM_ILLEGAL}, /* A3  */
    {49, AM_DIRECT}, /* A4 LDY */
    {47, AM_DIRECT}, /* A5 LDA */
    {48, AM_DIRECT}, /* A6 LDX */
    {79, AM_DIRECT | 0x80}, /* A7 SMB2 */
    {91, AM_IMPLICIT}, /* A8 TAY */
    {47, AM_IMMEDIATE}, /* A9 LDA */
    {90, AM_IMPLICIT}, /* AA TAX */
    {0, AM_ILLEGAL}, /* AB  */
    {49, AM_ABSOLUTE}, /* AC LDY */
    {47, AM_ABSOLUTE}, /* AD LDA */
    {48, AM_ABSOLUTE}, /* AE LDX */
    {14, AM_BITBRANCH | 0x80}, /* AF BBS2 */
    {21, AM_RELATIVE}, /* B0 BCS */
    {47, AM_DIRECTINDIRECTY}, /* B1 LDA */
    {47, AM_DIRECTINDIRECT | 0x80}, /* B2 LDA */
    {0, AM_ILLEGAL}, /* B3  */
    {49, AM_DIRECTX}, /* B4 LDY */
    {47, AM_DIRECTX}, /* B5 LDA */
    {48, AM_DIRECTY}, /* B6 LDX */
    {80, AM_DIRECT | 0x80}, /* B7 SMB3 */
    {34, AM_IMPLICIT}, /* B8 CLV */
    {47, AM_ABSOLUTEY}, /* B9 LDA */
    {94, AM_IMPLICIT}, /* BA TSX */
    {0, AM_ILLEGAL}, /* BB  */
    {49, AM_ABSOLUTEX}, /* BC LDY */
    {47, AM_ABSOLUTEX}, /* BD LDA */
    {48, AM_ABSOLUTEY}, /* BE LDX */
    {15, AM_BITBRANCH | 0x80}, /* BF BBS3 */
    {37, AM_IMMEDIATE}, /* C0 CPY */
    {35, AM_DIRECTXINDIRECT}, /* C1 CMP */
    {0, AM_ILLEGAL}, /* C2  */
    {0, AM_ILLEGAL}, /* C3  */
    {37, AM_DIRECT}, /* C4 CPY */
    {35, AM_DIRECT}, /* C5 CMP */
    {38, AM_DIRECT}, /* C6 DEC */
    {81, AM_DIRECT | 0x80}, /* C7 SMB4 */
    {44, AM_IMPLICIT}, /* C8 INY */
    {35, AM_IMMEDIATE}, /* C9 CMP */
    {39, AM_IMPLICIT}, /* CA DEX */
    {98, AM_IMPLICIT | 0x80}, /* CB WAI */
    {37, AM_ABSOLUTE}, /* CC CPY */
    {35, AM_ABSOLUTE}, /* CD CMP */
    {38, AM_ABSOLUTE}, /* CE DEC */
    {16, AM_BITBRANCH | 0x80}, /* CF BBS4 */
    {25, AM_RELATIVE}, /* D0 BNE */
    {35, AM_DIRECTINDIRECTY}, /* D1 CMP */
    {35, AM_DIRECTINDIRECT | 0x80}, /* D2 CMP */
    {0, AM_ILLEGAL}, /* D3  */
    {0, AM_ILLEGAL}, /* D4  */
    {35, AM_DIRECTX}, /* D5 CMP */
    {38, AM_DIRECTX}, /* D6 DEC */
    {82, AM_DIRECT | 0x80}, /* D7 SMB5 */
    {32, AM_IMPLICIT}, /* D8 CLD */
    {35, AM_ABSOLUTEY}, /* D9 CMP */
    {55, AM_IMPLICIT | 0x80}, /* DA PHX */
    {86, AM_IMPLICIT | 0x80}, /* DB STP */
    {0, AM_ILLEGAL}, /* DC  */
    {35, AM_ABSOLUTEX}, /* DD CMP */
    {38, AM_ABSOLUTEX}, /* DE DEC */
    {17, AM_BITBRANCH | 0x80}, /* DF BBS5 */
    {36, AM_IMMEDIATE}, /* E0 CPX */
    {73, AM_DIRECTXINDIRECT}, /* E1 SBC */
    {0, AM_ILLEGAL}, /* E2  */
    {0, AM_ILLEGAL}, /* E3  */
    {36, AM_DIRECT}, /* E4 CPX */
    {73, AM_DIRECT}, /* E5 SBC */
    {42, AM_DIRECT}, /* E6 INC */
    {83, AM_DIRECT | 0x80}, /* E7 SMB6 */
    {43, AM_IMPLICIT}, /* E8 INX */
    {73, AM_IMMEDIATE}, /* E9 SBC */
    {51, AM_IMPLICIT}, /* EA NOP */
    {0, AM_ILLEGAL}, /* EB  */
    {36, AM_ABSOLUTE}, /* EC CPX */
    {73, AM_ABSOLUTE}, /* ED SBC */
    {42, AM_ABSOLUTE}, /* EE INC */
    {18, AM_BITBRANCH | 0x80}, /* EF BBS6 */
    {22, AM_RELATIVE}, /* F0 BEQ */
    {73, AM_DIRECTINDIRECTY}, /* F1 SBC */
    {73, AM_DIRECTINDIRECT | 0x80}, /* F2 SBC */
    {0, AM_ILLEGAL}, /* F3  */
    {0, AM_ILLEGAL}, /* F4  */
    {73, AM_DIRECTX}, /* F5 SBC */
    {42, AM_DIRECTX}, /* F6 INC */
    {84, AM_DIRECT | 0x80}, /* F7 SMB7 */
    {75, AM_IMPLICIT}, /* F8 SED */
    {73, AM_ABSOLUTEY}, /* F9 SBC */
    {59, AM_IMPLICIT | 0x80}, /* FA PLX */
    {0, AM_ILLEGAL}, /* FB  */
    {0, AM_ILLEGAL}, /* FC  */
    {73, AM_ABSOLUTEX}, /* FD SBC */
    {42, AM_ABSOLUTEX}, /* FE INC */
    {19, AM_BITBRANCH | 0x80}, /* FF BBS7 */
};

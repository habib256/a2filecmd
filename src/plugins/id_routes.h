struct Route {const char* label;const char* view;};
static const struct Route routes[]={
 {"PFS:Write","PFSWRITE"},{"PFS:File","PFSFILE"},{"PFS:Plan","PFSPLAN"},
 {"LISA 8/16","LISAV4"},{"MGTK","FONTVIEW"},{"Purplesoft","PURPLE"},{"LZ4FH","LZ4FH"},
 {"Print Shop","PRINTSHOP"},{"Lo-res","DGRVIEW"},{"DGR pixmap","DGRVIEW"},
 {"ProTracker","PT3"},{"Electric Duet compatible","DUET"},{"Markdown","MDVIEW"},
 {"Applesoft","BASLIST"},{"Integer BASIC","INTBASIC"},{"HGR picture","IMAGE"},
 {"DHGR picture","IMAGE"},{"Packed","PACKFOT"},{"Extasie","EXTASIE"},
 {"816/Paint","PAINT816"},{"Hi-res","IMAGE"},{"Mockingboard","MUSIC"},
 {"AppleWorks word","AWP"},{"AppleWorks data","AWDATA"},{"AppleWorks spreadsheet","AWDATA"},
 {"ProDOS system","DISASM"},{"Binary, maybe","DISASM"},{"Text","TEXT"}
};
static void route(const char* label){
 unsigned char i;for(i=0;i<sizeof(routes)/sizeof(routes[0]);++i)
  if(!strncmp(label,routes[i].label,strlen(routes[i].label))){reader=routes[i].view;return;}
 reader="HEX";
}

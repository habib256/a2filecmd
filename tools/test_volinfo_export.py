"""Run VOLINFO's real E export (export_report) over host mocks: the report
is reserved by an exclusive CREATE, a name in use is never opened or
truncated, and write/close/open faults are reported, never called a saved
report. Checks the bytes on disk, not just the message."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#define __fastcall__
#define VOLINFO_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#define ferror mock_ferror
static int mock_ferror(FILE*);
#include "src/plugins/volinfo.c"
int close(int);   /* not <unistd.h>: its fork() clashes with the walker's */
static int fault, writes, wb_opens, removes,dir_fault,dir_opens,dir_closes;
static FILE* directory;
static FILE* errored;
static int mock_ferror(FILE* f) { return f == errored; }
static char msg[128], errmsg[64], in[80], outfull[256];
static unsigned char scratch[512], ft; static unsigned int at;
static unsigned char mock_mli(unsigned char cmd, void* p) {
    struct Create* c = p; char path[80]; int fd;
    if (cmd != 0xC0) abort();             /* the export reads no block */
    memcpy(path, c->path + 1, c->path[0]); path[c->path[0]] = 0;
    fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return 0x47;
    close(fd); return 0;
}
static FILE* mock_fopen(const char* p, const char* m) {
    if(!strcmp(p,"S")){
        ++dir_opens;if(dir_fault==5)return NULL;
        directory=fopen(p,m);return directory;
    }
    if (!strcmp(m, "wb")) { ++wb_opens; if (fault & 4) return NULL; }
    return fopen(p, m);
}
static size_t mock_fread(void* p,size_t s,size_t n,FILE* f){
    if(f==directory){
        if(dir_fault==3){errored=f;return 0;}
        if(dir_fault==2)n/=2;
        if(dir_fault==1)errored=f;
    }
    return fread(p,s,n,f);
}
static size_t mock_fwrite(const void* p, size_t s, size_t n, FILE* f) {
    ++writes;
    if (fault & 1) return fwrite(p, s, n / 2, f);       /* disk full on the first write */
    if (writes == fault / 16) errored = f; /* full count plus stream error */
    return fwrite(p, s, n, f);
}
static int mock_fclose(FILE* f) {
    int bad=f==directory && dir_fault==4;
    if(f==directory){++dir_closes;directory=NULL;}
    if(f==errored)errored=NULL;
    int r=fclose(f);return (fault & 2) || bad ? -1 : r;
}
static int mock_remove(const char* p) { ++removes; return (fault & 8) ? -1 : remove(p); }
static void mock_message(const char* s) { strcpy(msg, s); }
static void mock_report(const char* s) { snprintf(errmsg, sizeof errmsg, "%s failed", s); }
static char mock_cgetc(void) { return 13; }
static unsigned char mock_prompt(const char* q, const char* d, unsigned char h) { strcpy(in, d); return 1; }
int main(int argc, char** argv) {
    struct A2fcApi api = {0};
    struct Panel panels[2] = {{0}};
    struct Entry selected = {{0}};
    unsigned char active = 0;
    fault = atoi(argv[1]);
    dir_fault=argc>2?atoi(argv[2]):0;
    api.mli = mock_mli; api.memcpy = memcpy; api.memset = memset; api.strlen = strlen;
    api.strcmp = strcmp; api.sprintf = sprintf; api.fopen = mock_fopen; api.fread = mock_fread;
    api.fwrite = mock_fwrite; api.fclose = mock_fclose; api.remove = mock_remove;
    api.message = mock_message; api.report_error = mock_report; api.cgetc = mock_cgetc;
    api.prompt = mock_prompt; api.input = in; api.other_full = outfull;
    api.filetype = &ft; api.auxtype = &at;
    api.panels = panels; api.active = &active; api.selected = &selected;
    strcpy(panels[0].path, "/V"); strcpy(panels[1].path, "out");
    if(argc>2){strcpy(panels[0].path,"S");strcpy(selected.name,"DATA");selected.type=6;}
    A = &api; buf = scratch; strcpy(volume, "/V"); total = 280; freeblocks = 200;
    export_report();
    printf("%s|%s|%d|%d|%d\n", msg, errmsg, wb_opens, removes, writes);
    fprintf(stderr,"DIRECTORY %d %d\n",dir_opens,dir_closes);
    return 0;
}
'''


class VolinfoExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='volinfo-export-')
        cls.work = Path(cls.tmp.name)
        (cls.work/'export.c').write_text(HARNESS)
        cls.exe = cls.work/'export'
        subprocess.run(['cc', '-std=c99', '-w', '-I', str(ROOT), str(cls.work/'export.c'),
                        '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_export(self, fault, existing=None, dir_fault=None,slot=1):
        d = Path(tempfile.mkdtemp(dir=self.work))
        (d/'out').mkdir()
        report = d/'out'/'VOLINFO.TXT'
        before=None
        if dir_fault is not None:
            data=bytearray(512);data[4:9]=b'\xe4DATA'
            at=4+39*slot;data[at:at+5]=b'\x14DATA'
            data[at+16]=6;data[at+17:at+19]=(20).to_bytes(2,'little')
            data[at+19:at+21]=(1).to_bytes(2,'little')
            (d/'S').write_bytes(data)
            (d/'out'/'KEEP').write_bytes(b'unrelated bytes')
            before=bytes(data)
        if existing is not None:
            report.write_bytes(existing)
        args=[str(self.exe),str(fault)]+([] if dir_fault is None else [str(dir_fault)])
        run=subprocess.run(args,cwd=d,timeout=10,text=True,capture_output=True,check=True)
        out=run.stdout.strip()
        self.directory_state=tuple(map(int,run.stderr.split()[1:]))
        if before is not None:
            self.assertEqual((d/'S').read_bytes(),before)
            self.assertEqual((d/'out'/'KEEP').read_bytes(),b'unrelated bytes')
        msg, err, wb, removes, writes = out.split('|')
        return report, msg, err, int(wb), int(removes), int(writes)

    def test_complete_report_ends_with_its_marker(self):
        report, msg, err, wb, rm, _ = self.run_export(0)
        text = report.read_bytes()
        self.assertTrue(text.startswith(b'VOLINFO /V\r\nBlocks: 280   Free: 200'), text)
        self.assertTrue(text.endswith(b'END REPORT\r\n'), text)
        self.assertEqual((msg, wb, rm), ('Report saved in other panel.', 1, 0))

    def test_name_in_use_is_never_opened_or_truncated(self):
        old = b'precious bytes \x00\xff' * 40
        report, msg, err, wb, rm, writes = self.run_export(0, existing=old)
        self.assertEqual(report.read_bytes(), old)
        self.assertEqual((msg, wb, rm, writes), ('Cannot create report (name in use?).', 0, 0, 0))

    def test_disk_full_is_a_partial_report_without_end_marker(self):
        report, msg, err, wb, rm, _ = self.run_export(1)
        self.assertEqual(msg, 'Partial report (error/cancelled).')
        self.assertNotIn(b'END REPORT', report.read_bytes())

    def test_full_count_with_stream_error_is_a_partial_report(self):
        for at in (1, 2):  # summary and END REPORT
            with self.subTest(write=at):
                report, msg, err, wb, rm, writes = self.run_export(at * 16)
                self.assertEqual(msg, 'Partial report (error/cancelled).')
                self.assertEqual((wb, rm, writes), (1, 0, at))
                self.assertTrue(report.read_bytes().startswith(b'VOLINFO /V\r\n'))
                if at == 1:
                    self.assertNotIn(b'END REPORT', report.read_bytes())

    def test_close_error_is_not_a_saved_report(self):
        report, msg, err, wb, rm, _ = self.run_export(2)
        self.assertEqual(msg, 'Partial report (error/cancelled).')

    def test_open_failure_removes_only_the_reserved_entry(self):
        report, msg, err, wb, rm, writes = self.run_export(4)
        self.assertFalse(report.exists())
        self.assertEqual((rm, writes, err), (1, 0, 'Report failed'))

    def test_open_failure_with_failed_cleanup_names_the_kept_file(self):
        report, msg, err, wb, rm, writes = self.run_export(4 | 8)
        self.assertTrue(report.exists())
        self.assertEqual(report.read_bytes(), b'')
        self.assertEqual((msg, rm, writes), ('Report failed; empty file kept.', 1, 0))

    def test_directory_errors_refuse_entry_and_complete_report_marker(self):
        for slot in (1,6,12):
            for fault in range(1,6):
                with self.subTest(slot=slot,fault=fault):
                    report,msg,err,wb,rm,writes=self.run_export(0,dir_fault=fault,slot=slot)
                    self.assertEqual(msg,'Partial report (error/cancelled).')
                    self.assertEqual((wb,rm,writes),(1,0,1))
                    self.assertEqual(self.directory_state,(1,0 if fault==5 else 1))
                    text=report.read_bytes()
                    self.assertTrue(text.startswith(b'VOLINFO /V\r\n'))
                    self.assertNotIn(b'FILE DATA:',text)
                    self.assertNotIn(b'END REPORT',text)
                    self.assertNotIn(b' ($0014)',text)
                    old=b'previous report\x00\xff'*40
                    kept,msg,err,wb,rm,writes=self.run_export(0,existing=old,dir_fault=fault,slot=slot)
                    self.assertEqual(kept.read_bytes(),old)
                    self.assertEqual((wb,rm,writes),(0,0,0))
                    self.assertEqual(self.directory_state,(0,0))

    def test_clean_directory_entry_can_still_export_its_blocks(self):
        for slot in (1,6,12):
            report,msg,err,wb,rm,writes=self.run_export(0,dir_fault=0,slot=slot)
            self.assertEqual(msg,'Report saved in other panel.')
            self.assertEqual(self.directory_state,(1,1))
            text=report.read_bytes()
            self.assertIn(b'FILE DATA:',text)
            self.assertIn(b'D    20 ($0014)',text)
            self.assertTrue(text.endswith(b'END REPORT\r\n'))


if __name__ == '__main__':
    unittest.main()

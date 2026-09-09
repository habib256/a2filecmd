// Render docs/MANUAL.md on macOS using the system PDF and text frameworks.
// swift tools/manual_pdf.swift docs/MANUAL.md docs/A2FILECMD-MANUAL-EN.pdf
import Foundation
import CoreGraphics
import CoreText
import PDFKit

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: swift tools/manual_pdf.swift INPUT.md OUTPUT.pdf\n", stderr)
    exit(2)
}
let dateFormatter = DateFormatter()
dateFormatter.locale = Locale(identifier: "en_US_POSIX")
dateFormatter.dateFormat = "d MMMM yyyy"
let generatedDate = dateFormatter.string(from: Date())
let input = CommandLine.arguments[1], output = CommandLine.arguments[2]
let source = try String(contentsOfFile: input, encoding: .utf8)
let W: CGFloat = 595.28, H: CGFloat = 841.89, margin: CGFloat = 46
let width = W - 2 * margin
let ink = CGColor(gray: 0.16, alpha: 1)
let blue = CGColor(red: 0.12, green: 0.28, blue: 0.40, alpha: 1)
var rect = CGRect(x: 0, y: 0, width: W, height: H)
let url = URL(fileURLWithPath: output)
let consumer = CGDataConsumer(url: url as CFURL)!
let ctx = CGContext(consumer: consumer, mediaBox: &rect, [kCGPDFContextTitle: "A2 File Cmd — Complete Manual", kCGPDFContextAuthor: "Arnaud Verhille", kCGPDFContextSubject: "Printable edition of docs/MANUAL.md"] as CFDictionary)!
var page = 0, y: CGFloat = 0
var headings: [(String, Int, CGFloat)] = []
func plain(_ s: String) -> String {
    var t = s.replacingOccurrences(of: #"\[([^\]]+)\]\(([^)]+)\)"#, with: "$1", options: .regularExpression)
    t = t.replacingOccurrences(of: "\\*", with: "*")
    return t.replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "`", with: "")
}
func attributed(_ s: String, _ size: CGFloat = 10.3, _ font: String = "ArialMT", _ color: CGColor = ink) -> NSAttributedString {
    let result = NSMutableAttributedString(string: "")
    let regex = try! NSRegularExpression(pattern: #"(\*\*.+?\*\*|`[^`]+`)"#)
    let ns = s as NSString
    var cursor = 0
    func append(_ text: String, _ family: String, _ point: CGFloat) {
        result.append(NSAttributedString(string: plain(text), attributes: [NSAttributedString.Key(kCTFontAttributeName as String): CTFontCreateWithName(family as CFString, point, nil), NSAttributedString.Key(kCTForegroundColorAttributeName as String): color]))
    }
    for match in regex.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
        if match.range.location > cursor { append(ns.substring(with: NSRange(location: cursor, length: match.range.location-cursor)), font, size) }
        let segment = ns.substring(with: match.range)
        append(segment, segment.hasPrefix("`") ? "Menlo-Regular" : "Arial-BoldMT", segment.hasPrefix("`") ? size * 0.91 : size)
        cursor = NSMaxRange(match.range)
    }
    if cursor < ns.length { append(ns.substring(from: cursor), font, size) }
    return result
}
func height(_ text: NSAttributedString, _ w: CGFloat) -> CGFloat {
    let setter = CTFramesetterCreateWithAttributedString(text)
    return ceil(CTFramesetterSuggestFrameSizeWithConstraints(setter, CFRange(location: 0, length: 0), nil, CGSize(width: w, height: 100000), nil).height) + 3
}
func draw(_ text: NSAttributedString, _ x: CGFloat, _ top: CGFloat, _ w: CGFloat, _ h: CGFloat) {
    let path = CGPath(rect: CGRect(x: x, y: H-top-h, width: w, height: h), transform: nil)
    let frame = CTFramesetterCreateFrame(CTFramesetterCreateWithAttributedString(text), CFRange(location: 0, length: 0), path, nil)
    ctx.textMatrix = .identity
    CTFrameDraw(frame, ctx)
}
func newPage() {
    if page > 0 { ctx.endPDFPage() }
    page += 1; ctx.beginPDFPage(nil); y = 66
    draw(attributed("A2 FILE CMD  /  COMPLETE MANUAL", 8, "Arial-BoldMT", blue), margin, 27, width, 16)
    ctx.setStrokeColor(CGColor(gray: 0.8, alpha: 1)); ctx.setLineWidth(0.5)
    ctx.move(to: CGPoint(x: margin, y: H-48)); ctx.addLine(to: CGPoint(x: W-margin, y: H-48)); ctx.strokePath()
    draw(attributed("A2 File Cmd · English edition", 8), margin, H-35, width-45, 15)
    draw(attributed("\(page)", 8), W-margin-25, H-35, 25, 15)
}
func ensure(_ needed: CGFloat) { if y + needed > H-55 { newPage() } }
func paragraph(_ s: String, size: CGFloat = 10.3, font: String = "ArialMT", indent: CGFloat = 0, gap: CGFloat = 8) {
    let text = attributed(s, size, font)
    let h = height(text, width-indent)
    ensure(h+gap)
    draw(text, margin+indent, y, width-indent, h); y += h+gap
}
newPage()
y = 165
paragraph("A2 FILE CMD", size: 34, font: "Arial-BoldMT", gap: 18)
paragraph("The complete manual", size: 22, gap: 24)
paragraph("Two panels. One Apple II.", size: 15, gap: 36)
paragraph("6502 and 65C02 editions\nBOOT · EXTRA · XL", size: 13, gap: 35)
paragraph("By Arnaud Verhille\nGNU General Public License v3", size: 11, gap: 28)
paragraph("Printable edition of the project's English manual.\nSource: docs/MANUAL.md", size: 10, gap: 12)
paragraph("Generated \(generatedDate). This PDF reproduces the documentation available when it was generated; development may continue in the source manual.", size: 9)
// Reserve a contents page, filled with page references after pagination.
newPage()
let contentsIndex = page-1
newPage()
let lines = source.components(separatedBy: .newlines)
var i = 0
while i < lines.count {
    let line = lines[i]
    if line.trimmingCharacters(in: .whitespaces).isEmpty { i += 1; continue }
    if line.hasPrefix("#") {
        let level = line.prefix(while: {$0 == "#"}).count
        let title = String(line.dropFirst(level)).trimmingCharacters(in: .whitespaces)
        ensure(level <= 2 ? 100 : 70)
        y += level <= 2 ? 14 : 7
        if level <= 2 { headings.append((plain(title),page-1,y)) }
        paragraph(title, size: level <= 2 ? 18 : 13, font: "Arial-BoldMT", gap: 12)
        i += 1; continue
    }
    if line.hasPrefix("```") {
        i += 1; var code: [String] = []
        while i < lines.count && !lines[i].hasPrefix("```") { code.append(lines[i]); i += 1 }
        for l in code { paragraph(l.isEmpty ? " " : l, size: 8.4, font: "Menlo-Regular", indent: 10, gap: 2) }
        y += 8; i += 1; continue
    }
    if line.hasPrefix("|") {
        var rows: [[String]] = []
        while i < lines.count && lines[i].hasPrefix("|") {
            let cells = lines[i].split(separator: "|", omittingEmptySubsequences: false).dropFirst().dropLast().map { $0.trimmingCharacters(in: .whitespaces) }
            if !cells.allSatisfy({ $0.allSatisfy({ $0 == "-" || $0 == ":" || $0 == " " }) }) { rows.append(cells) }
            i += 1
        }
        if rows.isEmpty { continue }
        let count = rows[0].count
        let ratios: [CGFloat] = count == 2 ? [0.25,0.75] : (count == 3 ? [0.22,0.16,0.62] : Array(repeating: 1/CGFloat(count), count: count))
        func tableRow(_ cells: [String], header: Bool) {
            let texts = cells.enumerated().map { (j,s) in attributed(s, header ? 9 : 9.2, header ? "Arial-BoldMT" : "ArialMT") }
            let h = max(24, texts.enumerated().map { height($0.element, width*ratios[$0.offset]-14)+12 }.max() ?? 24)
            ensure(h)
            if header { ctx.setFillColor(CGColor(red:0.90,green:0.94,blue:0.96,alpha:1));ctx.fill(CGRect(x:margin,y:H-y-h,width:width,height:h)) }
            var x = margin
            for j in 0..<texts.count {
                draw(texts[j],x+7,y+6,width*ratios[j]-14,h-10)
                x += width*ratios[j]
            }
            ctx.setStrokeColor(CGColor(gray:0.80,alpha:1));ctx.setLineWidth(0.4)
            ctx.move(to:CGPoint(x:margin,y:H-y-h));ctx.addLine(to:CGPoint(x:W-margin,y:H-y-h));ctx.strokePath()
            y += h
        }
        tableRow(rows[0], header:true)
        for row in rows.dropFirst() {
            let h = row.enumerated().map { height(attributed($0.element,9.2),width*ratios[$0.offset]-14)+12 }.max() ?? 24
            if y+h > H-55 { newPage(); tableRow(rows[0],header:true) }
            tableRow(row,header:false)
        }
        y += 12; continue
    }
    var text = line; i += 1
    let bullet = line.hasPrefix("- ") || line.hasPrefix("* ")
    while i < lines.count && !lines[i].isEmpty && !lines[i].hasPrefix("#") && !lines[i].hasPrefix("|") && !lines[i].hasPrefix("```") && !lines[i].hasPrefix("- ") && !lines[i].hasPrefix("* ") {
        text += " " + lines[i].trimmingCharacters(in:.whitespaces); i += 1
    }
    if bullet { text = "• " + String(text.dropFirst(2)) }
    paragraph(text, indent: bullet ? 10 : 0)
}
ctx.endPDFPage();ctx.closePDF()
let document = PDFDocument(url:url)!
let root = PDFOutline()
for (title,index,top) in headings {
    let outline = PDFOutline(); outline.label = title
    outline.destination = PDFDestination(page:document.page(at:index)!,at:CGPoint(x:margin,y:H-top))
    root.insertChild(outline,at:root.numberOfChildren)
}
document.outlineRoot = root
// Add the contents as PDF annotations; text remains selectable.
let toc = document.page(at:contentsIndex)!
func annotation(_ text: String, _ x: CGFloat, _ top: CGFloat, _ width: CGFloat, _ size: CGFloat) {
    let h = max(24, size+18)
    let a = PDFAnnotation(bounds:CGRect(x:x,y:H-top-h,width:width,height:h),forType:.freeText,withProperties:nil)
    a.contents=text;a.font=NSFont(name:"Arial",size:size);a.fontColor=NSColor.black;a.color=NSColor.clear
    a.shouldPrint=true; toc.addAnnotation(a)
}
annotation("Contents",margin,80,width,24)
var top: CGFloat = 135
for (title,index,_) in headings {
    annotation(title,margin,top,width-45,10)
    annotation("\(index+1)",W-margin-30,top,30,10)
    let link = PDFAnnotation(bounds:CGRect(x:margin,y:H-top-24,width:width,height:24),forType:.link,withProperties:nil)
    link.destination = PDFDestination(page:document.page(at:index)!,at:CGPoint(x:margin,y:H-margin))
    toc.addAnnotation(link);top += 24
}
let finalURL = url.deletingPathExtension().appendingPathExtension("final.pdf")
if !document.write(to:finalURL) { fatalError("Cannot save PDF") }
try FileManager.default.removeItem(at:url);try FileManager.default.moveItem(at:finalURL,to:url)
print("Created \(output): \(document.pageCount) pages, \(headings.count) bookmarks")

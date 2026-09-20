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
let versionRange = source.range(of: #"(?<=\*\*Version )[0-9.]+"#, options: .regularExpression)
let guideVersion = versionRange.map { String(source[$0]) } ?? ""
let W: CGFloat = 595.28, H: CGFloat = 841.89, margin: CGFloat = 46
let width = W - 2 * margin
let ink = CGColor(gray: 0.16, alpha: 1)
let blue = CGColor(red: 0.12, green: 0.28, blue: 0.40, alpha: 1)
var rect = CGRect(x: 0, y: 0, width: W, height: H)
let url = URL(fileURLWithPath: output)
let consumer = CGDataConsumer(url: url as CFURL)!
let ctx = CGContext(consumer: consumer, mediaBox: &rect, [kCGPDFContextTitle: "A2 File Cmd — User Guide", kCGPDFContextAuthor: "Arnaud Verhille", kCGPDFContextSubject: "Printable edition of docs/MANUAL.md"] as CFDictionary)!
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
    draw(attributed("A2 FILE CMD  /  USER GUIDE", 8, "Arial-BoldMT", blue), margin, 27, width, 16)
    ctx.setStrokeColor(CGColor(gray: 0.8, alpha: 1)); ctx.setLineWidth(0.5)
    ctx.move(to: CGPoint(x: margin, y: H-48)); ctx.addLine(to: CGPoint(x: W-margin, y: H-48)); ctx.strokePath()
    draw(attributed("A2 File Cmd · English edition", 8), margin, H-35, width-45, 15)
    draw(attributed("\(page)", 8), W-margin-25, H-35, 25, 15)
}
func ensure(_ needed: CGFloat) { if y + needed > H-55 { newPage() } }
func paragraph(_ s: String, size: CGFloat = 10.3, font: String = "ArialMT", indent: CGFloat = 0, gap: CGFloat = 6) {
    let text = attributed(s, size, font)
    let h = height(text, width-indent)
    ensure(h+gap)
    draw(text, margin+indent, y, width-indent, h); y += h+gap
}
newPage()
y = 84
paragraph("A2 FILE CMD", size: 30, font: "Arial-BoldMT", gap: 12)
paragraph("User guide · \(guideVersion)", size: 19, gap: 16)
paragraph("ProDOS: 140K essential · 800K complete · XL 6502", size: 12, gap: 8)
paragraph("XL enhanced 65C02 with optional mouse · DOS3.3", size: 12, gap: 8)
if source.contains("— Preparation edition.") {
    paragraph("Preparation edition — release qualification in progress", size: 10, gap: 8)
}

let contentsIndex = page-1
newPage()
let lines = source.components(separatedBy: .newlines)
var i = 0
while i < lines.count {
    let line = lines[i]
    if line == "<!-- pagebreak -->" {
        newPage(); i += 1; continue
    }
    // Markdown has its own linked contents; the PDF uses the cover's page links.
    if line == "## Contents" {
        i += 1
        while i < lines.count && !lines[i].hasPrefix("## ") { i += 1 }
        continue
    }
    if line.hasPrefix("![") { i += 1; continue }
    if line.trimmingCharacters(in: .whitespaces).isEmpty { i += 1; continue }
    if line.hasPrefix("#") {
        let level = line.prefix(while: {$0 == "#"}).count
        let title = String(line.dropFirst(level)).trimmingCharacters(in: .whitespaces)
        if level == 1 { i += 1; continue }
        // Paragraphs are kept whole: reserve the first one with its heading,
        // otherwise a title can be stranded at the foot of the previous page.
        var next = i + 1
        while next < lines.count && lines[next].isEmpty { next += 1 }
        var firstText = ""
        while next < lines.count && !lines[next].isEmpty && !lines[next].hasPrefix("#") && !lines[next].hasPrefix("|") && !lines[next].hasPrefix("```") {
            if !firstText.isEmpty && (lines[next].hasPrefix("- ") || lines[next].range(of: #"^\d+\. "#, options: .regularExpression) != nil) { break }
            firstText += " " + lines[next]; next += 1
        }
        let firstHeight = firstText.isEmpty ? 65 : height(attributed(firstText), width-10)+6
        let titleHeight = height(attributed(title, level <= 2 ? 18 : 13, "Arial-BoldMT"), width)
        ensure(titleHeight + 22 + firstHeight)
        y += level <= 2 ? 10 : 5
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
        // The companion catalog needs room for lists of tools; volume names
        // are short identifiers. Other three-column tables describe commands.
        let companionCatalog = rows[0] == ["Category", "Plugins", "ProDOS volume"]
        let imageCatalog = rows[0] == ["Image", "Contents"] || rows[0] == ["Image", "Choose it for"]
        let recoveryCatalog = rows[0] == ["Operation", "New candidate", "Previous version"]
        let ratios: [CGFloat] = imageCatalog ? [0.55,0.45] : recoveryCatalog ? [0.34,0.33,0.33] : companionCatalog ? [0.18,0.55,0.27] :
            (count == 2 ? [0.25,0.75] : (count == 3 ? [0.22,0.16,0.62] : Array(repeating: 1/CGFloat(count), count: count)))
        func tableRow(_ cells: [String], header: Bool) {
            let texts = cells.enumerated().map { (j,s) in attributed(s, header ? 9 : 9.2, header ? "Arial-BoldMT" : "ArialMT") }
            let h = max(21, texts.enumerated().map { height($0.element, width*ratios[$0.offset]-14)+8 }.max() ?? 24)
            ensure(h)
            if header { ctx.setFillColor(CGColor(red:0.90,green:0.94,blue:0.96,alpha:1));ctx.fill(CGRect(x:margin,y:H-y-h,width:width,height:h)) }
            var x = margin
            for j in 0..<texts.count {
                draw(texts[j],x+7,y+4,width*ratios[j]-14,h-6)
                x += width*ratios[j]
            }
            ctx.setStrokeColor(CGColor(gray:0.80,alpha:1));ctx.setLineWidth(0.4)
            ctx.move(to:CGPoint(x:margin,y:H-y-h));ctx.addLine(to:CGPoint(x:W-margin,y:H-y-h));ctx.strokePath()
            y += h
        }
        tableRow(rows[0], header:true)
        for row in rows.dropFirst() {
            let h = row.enumerated().map { height(attributed($0.element,9.2),width*ratios[$0.offset]-14)+8 }.max() ?? 24
            if y+h > H-55 { newPage(); tableRow(rows[0],header:true) }
            tableRow(row,header:false)
        }
        y += 8; continue
    }
    var text = line; i += 1
    let bullet = line.hasPrefix("- ") || line.hasPrefix("* ")
    let numbered = line.range(of: #"^\d+\. "#, options: .regularExpression) != nil
    while i < lines.count && !lines[i].isEmpty && !lines[i].hasPrefix("#") && !lines[i].hasPrefix("|") && !lines[i].hasPrefix("```") && !lines[i].hasPrefix("- ") && !lines[i].hasPrefix("* ") && lines[i].range(of: #"^\d+\. "#, options: .regularExpression) == nil {
        text += " " + lines[i].trimmingCharacters(in:.whitespaces); i += 1
    }
    if bullet { text = "• " + String(text.dropFirst(2)) }
    paragraph(text, indent: bullet || numbered ? 10 : 0)
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
annotation("Contents",margin,270,width,18)
// The contents stop above the two credit lines below: with enough headings,
// the rows are set closer together instead of running into them.
let firstRow: CGFloat = 308, lastRow: CGFloat = 712
let step = min(28, (lastRow-firstRow)/CGFloat(max(headings.count-1,1)))
var top: CGFloat = firstRow
for (title,index,_) in headings {
    annotation(title,margin,top,width-45,10)
    annotation("\(index+1)",W-margin-30,top,30,10)
    let link = PDFAnnotation(bounds:CGRect(x:margin,y:H-top-step,width:width,height:step),forType:.link,withProperties:nil)
    link.destination = PDFDestination(page:document.page(at:index)!,at:CGPoint(x:margin,y:H-margin))
    toc.addAnnotation(link);top += step
}
annotation("By Arnaud Verhille · GNU GPL v3",margin,max(top+14,750),width,9)
annotation("English guide · Generated \(generatedDate)",margin,max(top+38,774),width,8)
let finalURL = url.deletingPathExtension().appendingPathExtension("final.pdf")
if !document.write(to:finalURL) { fatalError("Cannot save PDF") }
try FileManager.default.removeItem(at:url);try FileManager.default.moveItem(at:finalURL,to:url)
print("Created \(output): \(document.pageCount) pages, \(headings.count) bookmarks")

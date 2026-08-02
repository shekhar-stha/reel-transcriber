// Usage: swift ocr.swift <image-path>
// Prints recognized text lines (one per line), ordered top-to-bottom.
import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write("usage: ocr.swift <image>\n".data(using: .utf8)!)
    exit(2)
}
let imgPath = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: imgPath),
      let tiff = img.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let cg = bitmap.cgImage else {
    FileHandle.standardError.write("could not load image\n".data(using: .utf8)!)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("ocr failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}

guard let observations = request.results else { exit(0) }

// Sort top-to-bottom (Vision origin is bottom-left, so higher y = higher on screen)
let sorted = observations.sorted { $0.boundingBox.origin.y > $1.boundingBox.origin.y }
for obs in sorted {
    if let top = obs.topCandidates(1).first {
        print(top.string)
    }
}

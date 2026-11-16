/**
 * A photo for the chat (C.7, P5.3): at most 1,024 px on its longest side, re-encoded as
 * JPEG in the browser, so one small upload goes with the message. The server checks and
 * cleans it again; this only keeps uploads small on a phone's connection.
 */

export const MAX_SIDE = 1024
export const QUALITY = 0.85

/** The size to draw at: the longest side cut to `max`, never enlarged. */
export function fitSize(width, height, max = MAX_SIDE) {
  const scale = Math.min(1, max / Math.max(width, height))
  return { width: Math.round(width * scale), height: Math.round(height * scale) }
}

export async function shrinkPhoto(file) {
  const bitmap = await createImageBitmap(file)
  const { width, height } = fitSize(bitmap.width, bitmap.height)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height)
  bitmap.close()
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The photo could not be read.'))),
                  'image/jpeg', QUALITY)
  })
}

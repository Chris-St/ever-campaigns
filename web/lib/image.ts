const BLANK_IMAGE_SRC =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

export function fallbackImageSrc(src?: string | null): string {
  return src ?? BLANK_IMAGE_SRC;
}

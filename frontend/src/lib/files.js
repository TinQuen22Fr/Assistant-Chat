export const MAX_FILE_MB = 20;
export const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
export const ACCEPTED_EXT = [".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"];
export const ACCEPT_ATTR = ACCEPTED_EXT.join(",");

export const formatSize = (bytes) => {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;
};

export const isImage = (file) => /\.(png|jpe?g|webp)$/i.test(file.name);

export function validateFile(file) {
  const ext = `.${file.name.split(".").pop().toLowerCase()}`;
  if (!ACCEPTED_EXT.includes(ext)) {
    return `Format non pris en charge pour « ${file.name} ». Formats acceptés : PDF, DOCX, TXT, MD, PNG, JPG, WEBP.`;
  }
  if (file.size > MAX_FILE_BYTES) {
    return `Le fichier « ${file.name} » dépasse la limite autorisée de ${MAX_FILE_MB} Mo (${formatSize(file.size)}).`;
  }
  return null;
}

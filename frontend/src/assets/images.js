// Centralized image assets configuration
// All images are stored in public/Images/ directory

// Base path for images
const IMAGE_BASE_PATH = '/Images';

// Image asset mappings
// TODO: Download these images from Figma and save them to public/Images/ with these filenames
export const images = {
  // Magic pen icons
  magicPen: `${IMAGE_BASE_PATH}/dashboardpagemainicon.png`, // Large icon for dashboard main heading
  magicPenIcon: `${IMAGE_BASE_PATH}/magic-pen-icon.png`, // Small icon for headers/sidebar
  
  // Navigation sidebar icons
  dashboard: `${IMAGE_BASE_PATH}/dashboard.png`,
  history: `${IMAGE_BASE_PATH}/history.png`,
  tokens: `${IMAGE_BASE_PATH}/tokens.png`,
  settings: `${IMAGE_BASE_PATH}/settings.png`,
  sidebar: `${IMAGE_BASE_PATH}/sidebar.png`,
  logout: `${IMAGE_BASE_PATH}/logout.png`,
  avatar: `${IMAGE_BASE_PATH}/avatar.png`,
  
  // PDF Translator icons
  pdfIcon: `${IMAGE_BASE_PATH}/pdf-icon.png`, // PDF icon in headings
  pdfIconContent: `${IMAGE_BASE_PATH}/pdf-icon-content.png`, // PDF icon for content areas
  translateIcon: `${IMAGE_BASE_PATH}/translate-icon.png`, // Upload area icon
  translateIconHeading: `${IMAGE_BASE_PATH}/codingicon.png`, // Translate icon in heading (after "Translate" text)
  uploadFrame: `${IMAGE_BASE_PATH}/upload-frame.png`, // Upload area frame (still needed)
  fileIcon: `${IMAGE_BASE_PATH}/file-icon.png`,
  fileClose: `${IMAGE_BASE_PATH}/file-close.png`,
  
  // Tab icons
  pdfTab: `${IMAGE_BASE_PATH}/pdf-tab.png`,
  solutionTab: `${IMAGE_BASE_PATH}/pdf-tab.png`, // Solution generator tab uses pdf-tab.png
  mcqTab: `${IMAGE_BASE_PATH}/mcqgenerator.png`, // MCQ generator tab uses mcqgenerator.png
  
  // Solution Generator icons
  solutionIcon: `${IMAGE_BASE_PATH}/solution-icon.png`,
  
  // MCQ Generator icons
  mcqIcon: `${IMAGE_BASE_PATH}/mcqgenerator.png`, // MCQ generator icon
  mcqMinus: `${IMAGE_BASE_PATH}/mcq-minus.png`,
  mcqPlus: `${IMAGE_BASE_PATH}/mcq-plus.png`,
  mcqInfo: `${IMAGE_BASE_PATH}/mcq-info.png`,
  mcqBin: `${IMAGE_BASE_PATH}/mcq-bin.png`,
  mcqAddPlus: `${IMAGE_BASE_PATH}/mcq-add-plus.png`,
  mcqToggle: `${IMAGE_BASE_PATH}/mcq-toggle.png`,
  
  // History page icons
  file: `${IMAGE_BASE_PATH}/file.png`,
  plus: `${IMAGE_BASE_PATH}/plus.png`,
  translate: `${IMAGE_BASE_PATH}/translate.png`,
  chevronRight: `${IMAGE_BASE_PATH}/chevron-right.png`,
  pdfIconHistory: `${IMAGE_BASE_PATH}/pdf-icon-history.png`,
  infoIcon: `${IMAGE_BASE_PATH}/info-icon.png`,
  successIcon: `${IMAGE_BASE_PATH}/success-icon.png`,
  statusDot: `${IMAGE_BASE_PATH}/status-dot.png`,
  calendar: `${IMAGE_BASE_PATH}/calendar.png`,
  retry: `${IMAGE_BASE_PATH}/retry.png`,
  arrowLeft: `${IMAGE_BASE_PATH}/arrow-left.png`,
  arrowRight: `${IMAGE_BASE_PATH}/arrow-right.png`,
  checkbox: `${IMAGE_BASE_PATH}/checkbox.png`,
  search: `${IMAGE_BASE_PATH}/search.png`,
  
  // PDF Output icons
  menu: `${IMAGE_BASE_PATH}/menu.png`,
  minus: `${IMAGE_BASE_PATH}/minus.png`,
  plusOutput: `${IMAGE_BASE_PATH}/plus-output.png`,
  rotate: `${IMAGE_BASE_PATH}/rotate.png`,
  presentation: `${IMAGE_BASE_PATH}/presentation.png`,
  download: `${IMAGE_BASE_PATH}/download.png`,
  print: `${IMAGE_BASE_PATH}/print.png`,
  dots: `${IMAGE_BASE_PATH}/dots.png`,
  line: `${IMAGE_BASE_PATH}/line.png`,
  line3: `${IMAGE_BASE_PATH}/line3.png`,
  edit: `${IMAGE_BASE_PATH}/edit.png`,
  downloadCloud: `${IMAGE_BASE_PATH}/download-cloud.png`,
  star: `${IMAGE_BASE_PATH}/star.png`,
};

// Fallback function to handle missing images
export const getImage = (imageKey, fallback = null) => {
  const imagePath = images[imageKey];
  if (!imagePath) {
    console.warn(`Image key "${imageKey}" not found in images mapping`);
    return fallback || `${IMAGE_BASE_PATH}/placeholder.png`;
  }
  return imagePath;
};


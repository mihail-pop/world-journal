document.querySelector("[data-print-document]").addEventListener("click", () => window.print());
const images = [...document.images];
for (const image of images) image.loading = "eager";
await Promise.all([document.fonts.ready, ...images.map(image => image.decode().catch(() => {}))]);
window.print();

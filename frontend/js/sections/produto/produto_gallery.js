export function setupGallery(section) {
    const mainImage = section.querySelector(
        ".produto__main-image img"
    );

    const thumbnails = section.querySelectorAll(
        ".produto__thumbnail"
    );

    if (!mainImage || !thumbnails.length) return;

    thumbnails.forEach((thumbnail) => {
        thumbnail.addEventListener("click", () => {
            mainImage.src = thumbnail.dataset.image;

            thumbnails.forEach((item) => {
                item.classList.remove("is-active");
            });

            thumbnail.classList.add("is-active");
        });
    });
}
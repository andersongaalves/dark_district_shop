import { escapeHtml } from "../../utils/dom.js";
export function renderDescription(description) {
    if (!description) {
        return "";
    }

    const lines = description
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

    const sections = [];
    let currentSection = null;

    lines.forEach((line) => {
        if (line.startsWith("-")) {
            if (!currentSection) {
                currentSection = {
                    title: null,
                    items: []
                };

                sections.push(currentSection);
            }

            currentSection.items.push(
                line.replace(/^-\s*/, "")
            );

            return;
        }

        currentSection = {
            title: line,
            items: []
        };

        sections.push(currentSection);
    });

    return sections
        .map((section) => {
            const title = section.title
                ? `
                    <h3 class="produto__description-title">
                        ${escapeHtml(section.title)}
                    </h3>
                `
                : "";

            const items = section.items.length
                ? `
                    <ul class="produto__description-list">
                        ${section.items.map(
                            (item) => `
                                <li>
                                    ${escapeHtml(item)}
                                </li>
                            `
                        ).join("")}
                    </ul>
                `
                : "";

            return `
                <div class="produto__description-section">
                    ${title}
                    ${items}
                </div>
            `;
        })
        .join("");
}
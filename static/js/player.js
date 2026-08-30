const MINIMIZED_KEY = "world-journal:player-minimized";

function setMinimized(player, minimized) {
    player.classList.toggle("is-minimized", minimized);
    player.querySelector("[data-player-minimize]")?.setAttribute("aria-label", minimized ? "Restore video player" : "Minimize video player");
    document.querySelector("[data-player-toggle]")?.setAttribute("aria-expanded", String(!minimized));

    try {
        localStorage.setItem(MINIMIZED_KEY, String(minimized));
    } catch (error) {
        // Player controls remain usable when storage is unavailable.
    }
}

export function initializePlayer() {
    const player = document.querySelector("#persistent-player");
    if (!player) {
        return;
    }

    let minimized = false;
    try {
        minimized = localStorage.getItem(MINIMIZED_KEY) === "true";
    } catch (error) {
        minimized = false;
    }
    setMinimized(player, minimized);

    player.querySelector("[data-player-minimize]")?.addEventListener("click", () => {
        setMinimized(player, !player.classList.contains("is-minimized"));
    });
    document.querySelector("[data-player-toggle]")?.addEventListener("click", () => setMinimized(player, false));
    player.querySelector("[data-player-close]")?.addEventListener("click", () => {
        player.dataset.playerState = "empty";
        player.querySelector("[data-player-actions]")?.setAttribute("hidden", "");
        document.querySelector("[data-player-toggle]")?.setAttribute("hidden", "");
    });
}
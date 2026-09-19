document.addEventListener("click", async (event) => {
  const button = event.target.closest(".generate");
  if (!button) return;
  button.disabled = true;
  button.textContent = "Génération en cours...";
  try {
    const token = document.querySelector('meta[name="csrf-token"]').content;
    const response = await fetch(button.dataset.url, {
      method: "POST",
      headers: { "X-CSRFToken": token },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Erreur de génération");
    window.location.href = data.redirect;
  } catch (error) {
    button.disabled = false;
    button.textContent = "✦ Générer avec l’IA";
    window.alert(error.message);
  }
});

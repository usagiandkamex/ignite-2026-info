const panel = document.querySelector("[data-filters]");
const query = document.querySelector("#query");
const selects = [...panel.querySelectorAll("[data-filter]")];
const normalize = (value) => value.normalize("NFKC").toLocaleLowerCase("ja").trim();
const records = [...document.querySelectorAll("[data-result]")].map((element) => ({
  element,
  text: normalize(element.dataset.text),
  facets: selects.map(({ dataset }) => element.dataset[dataset.filter].split("|")),
}));
const count = panel.querySelector("[data-count]");
const empty = document.querySelector("[data-empty]");
const clear = panel.querySelector("[data-clear-filters]");
const format = new Intl.NumberFormat("ja-JP");

function filter() {
  const words = normalize(query.value).split(/\s+/).filter(Boolean);
  const values = selects.map((select) => select.value);
  clear.disabled = query.value === "" && values.every((value) => !value);
  let visible = 0;
  for (const { element, text, facets } of records) {
    const matches = words.every((word) => text.includes(word))
      && values.every((value, i) => !value || facets[i].includes(value));
    element.hidden = !matches;
    if (matches) visible++;
  }
  count.textContent = `${format.format(visible)} / ${format.format(records.length)} 件を表示`;
  empty.hidden = visible !== 0;
}

query.addEventListener("input", filter);
panel.addEventListener("change", filter);
clear.addEventListener("click", () => {
  query.value = "";
  selects.forEach((select) => { select.value = ""; });
  filter();
  query.focus();
});
window.addEventListener("pageshow", filter);
filter();
panel.hidden = false;

(function () {
  var KEY = "savedArticles";

  function getSaved() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "[]");
    } catch (e) {
      return [];
    }
  }
  function setSaved(list) {
    localStorage.setItem(KEY, JSON.stringify(list));
  }
  function isSaved(link, list) {
    return list.some(function (a) { return a.link === link; });
  }

  // 카드의 ☆ 버튼을 누르면 저장/저장취소 토글
  window.toggleSave = function (btn) {
    var card = btn.closest(".article-card");
    var link = card.dataset.link;
    var list = getSaved();

    if (isSaved(link, list)) {
      list = list.filter(function (a) { return a.link !== link; });
      btn.textContent = "☆";
      btn.classList.remove("saved");
    } else {
      list.push({
        link: link,
        title: card.dataset.title,
        source: card.dataset.source,
        summary: card.dataset.summary,
        savedAt: new Date().toISOString(),
      });
      btn.textContent = "★";
      btn.classList.add("saved");
    }
    setSaved(list);
  };

  // 페이지 로드 시, 이미 저장된 기사는 ★로 표시
  document.addEventListener("DOMContentLoaded", function () {
    var list = getSaved();
    document.querySelectorAll(".article-card").forEach(function (card) {
      var btn = card.querySelector(".save-btn");
      if (btn && isSaved(card.dataset.link, list)) {
        btn.textContent = "★";
        btn.classList.add("saved");
      }
    });
  });
})();

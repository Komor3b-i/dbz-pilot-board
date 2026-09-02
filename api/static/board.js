// Auto-refresh the board every 30s, but stop once someone starts typing so a
// half-filled pilot / notes form is never wiped.
var timer = setTimeout(function () { location.reload(); }, 30000);

document.addEventListener('input', function () { clearTimeout(timer); });
document.addEventListener('focusin', function (e) {
  if (e.target.matches('input, select, textarea')) clearTimeout(timer);
});

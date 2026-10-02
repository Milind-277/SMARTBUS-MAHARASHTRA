// SmartBus Maharashtra - script.js

document.addEventListener('DOMContentLoaded', function () {

  // 1. Set min date = today for all date inputs
  var today = new Date().toISOString().split('T')[0];
  document.querySelectorAll('input[type="date"]').forEach(function (inp) {
    if (!inp.min) inp.min = today;
  });

  // 2. Auto-dismiss alerts after 5 seconds
  document.querySelectorAll('.alert').forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity 0.5s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 500);
    }, 5000);
  });

  // 3. Payment method panel toggle
  var payInputs = document.querySelectorAll('input[name="payment_method"]');
  if (payInputs.length) {
    payInputs.forEach(function (inp) {
      inp.addEventListener('change', function () {
        document.querySelectorAll('.pay-panel').forEach(function (p) {
          p.style.display = 'none';
        });
        var target = document.getElementById('panel-' + this.value.replace(/\s+/g, '-').toLowerCase());
        if (target) target.style.display = 'block';
      });
    });
    // Show first panel
    var first = document.querySelector('input[name="payment_method"]:checked');
    if (first) {
      var panel = document.getElementById('panel-' + first.value.replace(/\s+/g, '-').toLowerCase());
      if (panel) panel.style.display = 'block';
    }
  }
});

import "@testing-library/jest-dom/vitest";

// JSDOM has no native dialog implementation; browser tests exercise real focus trapping.
if (!HTMLDialogElement.prototype.showModal)
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
if (!HTMLDialogElement.prototype.close)
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };

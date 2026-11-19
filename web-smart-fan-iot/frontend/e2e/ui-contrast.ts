import type { Page } from '@playwright/test';
import { expect } from './fixtures';
import { writeFileSync } from 'node:fs';
export async function verifyContrast(page: Page, path: string) {
  const measureContrast = () =>
    page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const ctx = canvas.getContext('2d')!;
      const rgba = (color: string) => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 1, 1);
        return [...ctx.getImageData(0, 0, 1, 1).data];
      };
      const over = (top: number[], bottom: number[]) =>
        top
          .slice(0, 3)
          .map((v, i) => v * (top[3]! / 255) + bottom[i]! * (1 - top[3]! / 255))
          .concat(255);
      const lum = (rgb: number[]) =>
        rgb
          .slice(0, 3)
          .map((v) => {
            const n = v / 255;
            return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
          })
          .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i]!, 0);
      return [...document.querySelectorAll<HTMLElement>('.task-page *')]
        .filter(
          (el) =>
            el.checkVisibility({
              contentVisibilityAuto: true,
              visibilityProperty: true,
            }) &&
            el.getClientRects().length &&
            [...el.childNodes].some(
              (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim(),
            ) &&
            !el.closest(':disabled, .sr-only'),
        )
        .map((el) => {
          const style = getComputedStyle(el);
          let bg = [255, 255, 255, 255];
          const ancestors: Element[] = [];
          let parent: Element | null = el;
          while (parent) {
            ancestors.unshift(parent);
            parent = parent.parentElement;
          }
          for (const item of ancestors)
            bg = over(rgba(getComputedStyle(item).backgroundColor), bg);
          const fg = over(rgba(style.color), bg);
          const a = lum(fg),
            b = lum(bg);
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          const size = parseFloat(style.fontSize);
          const large =
            size >= 24 || (size >= 18.66 && parseInt(style.fontWeight) >= 700);
          return {
            text: el.innerText?.trim().slice(0, 90),
            color: style.color,
            background: bg.slice(0, 3),
            size,
            ratio: +ratio.toFixed(2),
            required: large ? 3 : 4.5,
          };
        });
    });
  const result = await measureContrast();
  writeFileSync(path, JSON.stringify(result, null, 2));
  expect(
    result.filter((item) => item.ratio < item.required || item.size < 14),
  ).toEqual([]);
}

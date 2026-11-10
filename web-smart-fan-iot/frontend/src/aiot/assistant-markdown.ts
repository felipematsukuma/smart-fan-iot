import MarkdownIt from 'markdown-it';
const markdown = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
  maxNesting: 12,
}).disable('image');
markdown.validateLink = (url: string) => {
  try {
    return ['https:', 'http:'].includes(new URL(url).protocol);
  } catch {
    return false;
  }
};
const original = markdown.renderer.rules.link_open;
markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index]!.attrSet('rel', 'noopener noreferrer');
  tokens[index]!.attrSet('target', '_blank');
  return original
    ? original(tokens, index, options, env, renderer)
    : renderer.renderToken(tokens, index, options);
};
/** HTML input stays escaped; only the parser's own fixed markup reaches v-html. */
export const safeMarkdown = (value: string) =>
  markdown.render(value.slice(0, 32768));

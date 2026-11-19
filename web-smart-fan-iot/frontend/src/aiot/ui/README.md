# Primitivas do piloto

Composições manuais baseadas em [shadcn-vue](https://www.shadcn-vue.com/), usando as primitivas Reka de Button/Sheet. Registro consultado: `new-york-v4` (Button e Sheet). Código adaptado à interface existente, sem cópia integral do scaffold ou importação de todos os componentes.

Tailwind é importado sem Preflight e com prefixo `ui:`. Nenhum token/reset global da instalação padrão é aplicado. `cn`, `@vueuse/core` e `tw-animate-css` não foram adicionados como dependências diretas nesta composição reduzida: não há encaminhamento genérico de classes/props nem animações do registro completo. As transitivas necessárias ao Reka permanecem no lock. Ícones reutilizam lucide-vue-next. Nenhuma biblioteca de gráfico/formulário foi adicionada.

Primitivas reutilizadas no shell e nas páginas aprovadas da rodada de UI/UX. Estilos adicionais ficam sob classes de página, sem reset global. O painel operacional preserva as variantes existentes e seus contratos.

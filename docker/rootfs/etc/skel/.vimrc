" orcan vim defaults — personal overrides in ~/.config/orcan/dotfiles/vimrc.local
" (host: $ORCAN_DATA/dotfiles/vimrc.local)

set encoding=UTF-8
set clipboard=unnamed
set mouse=""
set backspace=indent,eol,start
set number
set nohlsearch

set tabstop=4
set shiftwidth=4
set expandtab
set autoindent

syntax on
colorscheme desert

if filereadable(expand('~/.config/orcan/dotfiles/vimrc.local'))
  execute 'source' expand('~/.config/orcan/dotfiles/vimrc.local')
endif

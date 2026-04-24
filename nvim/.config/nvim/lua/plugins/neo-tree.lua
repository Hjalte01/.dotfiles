return {
  "nvim-neo-tree/neo-tree.nvim",
  opts = {
    filesystem = {
      filtered_items = {
        -- This is the magic switch! It shows the hidden items by default on startup.
        visible = true,

        -- Keep these set to true so Neo-tree still knows they belong to the toggle switch!
        hide_dotfiles = true,
        hide_gitignored = true,
        hide_hidden = true,
      },
    },
  },
}

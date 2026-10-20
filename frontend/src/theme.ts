import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    primary: { main: "#0f3d5e" },
    secondary: { main: "#d99a00" },
    background: { default: "#f4f6f9", paper: "#ffffff" },
    success: { main: "#15803d" },
    warning: { main: "#b45309" },
    error: { main: "#b91c1c" },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    h5: { fontWeight: 700 },
    h6: { fontWeight: 650 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiCard: { defaultProps: { variant: "outlined" } },
    MuiPaper: { styleOverrides: { outlined: { borderColor: "#e3e8ef" } } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 650, backgroundColor: "#f8fafc", whiteSpace: "nowrap" } } },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiChip: { defaultProps: { size: "small" } },
  },
});

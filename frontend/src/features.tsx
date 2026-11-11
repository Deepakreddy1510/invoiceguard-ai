import { createContext, useContext } from "react";

// Missing public configuration must never mount optional intake UI or requests.
export const EmailIntakeFeature = createContext(false);
export const useEmailIntake = () => useContext(EmailIntakeFeature);

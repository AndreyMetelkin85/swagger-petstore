/**
 *  Copyright 2018 SmartBear Software
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import java.util.Date;
import java.util.UUID;

@XmlRootElement(name = "User")
public class User {
  private UUID id;
  private String username;
  private String firstName;
  private String lastName;
  private String email;
  private String password;
  private String phone;
  private Address address;
  private AccountStatus userStatus = AccountStatus.PENDING;
  private Role role = Role.USER;
  private Date confirmedAt;
  private String confirmationCodeHash;
  private Date confirmationExpiresAt;
  private String resetCodeHash;
  private Date resetExpiresAt;
  private Date resetUsedAt;
  private int tokenVersion;

  @XmlElement(name = "id")
  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  @XmlElement(name = "firstName")
  public String getFirstName() {
    return firstName;
  }

  public void setFirstName(String firstName) {
    this.firstName = firstName;
  }

  @XmlElement(name = "username")
  public String getUsername() {
    return username;
  }

  public void setUsername(String username) {
    this.username = username;
  }

  @XmlElement(name = "lastName")
  public String getLastName() {
    return lastName;
  }

  public void setLastName(String lastName) {
    this.lastName = lastName;
  }

  @XmlElement(name = "email")
  public String getEmail() {
    return email;
  }

  public void setEmail(String email) {
    this.email = email;
  }

  @XmlElement(name = "password")
  @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
  public String getPassword() {
    return password;
  }

  public void setPassword(String password) {
    this.password = password;
  }

  @XmlElement(name = "phone")
  public String getPhone() {
    return phone;
  }

  public void setPhone(String phone) {
    this.phone = phone;
  }

  @XmlElement(name = "address")
  @JsonInclude(JsonInclude.Include.ALWAYS)
  public Address getAddress() {
    return address;
  }

  public void setAddress(final Address address) {
    this.address = address;
  }

  @XmlElement(name = "userStatus")
  @Schema(description = "Account lifecycle status")
  public AccountStatus getUserStatus() {
    return userStatus;
  }

  public void setUserStatus(AccountStatus userStatus) {
    this.userStatus = userStatus;
  }

  @XmlElement(name = "role")
  public Role getRole() {
    return role;
  }

  public void setRole(Role role) {
    this.role = role;
  }

  @JsonIgnore
  public Date getConfirmedAt() {
    return confirmedAt;
  }

  public void setConfirmedAt(Date confirmedAt) {
    this.confirmedAt = confirmedAt;
  }

  @JsonIgnore
  public String getConfirmationCodeHash() {
    return confirmationCodeHash;
  }

  public void setConfirmationCodeHash(String confirmationCodeHash) {
    this.confirmationCodeHash = confirmationCodeHash;
  }

  @JsonIgnore
  public Date getConfirmationExpiresAt() {
    return confirmationExpiresAt;
  }

  public void setConfirmationExpiresAt(Date confirmationExpiresAt) {
    this.confirmationExpiresAt = confirmationExpiresAt;
  }

  @JsonIgnore
  public String getResetCodeHash() {
    return resetCodeHash;
  }

  public void setResetCodeHash(String resetCodeHash) {
    this.resetCodeHash = resetCodeHash;
  }

  @JsonIgnore
  public Date getResetExpiresAt() {
    return resetExpiresAt;
  }

  public void setResetExpiresAt(Date resetExpiresAt) {
    this.resetExpiresAt = resetExpiresAt;
  }

  @JsonIgnore
  public Date getResetUsedAt() {
    return resetUsedAt;
  }

  public void setResetUsedAt(Date resetUsedAt) {
    this.resetUsedAt = resetUsedAt;
  }

  @JsonIgnore
  public int getTokenVersion() {
    return tokenVersion;
  }

  public void setTokenVersion(int tokenVersion) {
    this.tokenVersion = tokenVersion;
  }
}
